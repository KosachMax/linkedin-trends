from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from trends.ai.dedupe_service import DedupeService
from trends.ai.gemini import GeminiProvider
from trends.ai.service import EventSynthesisService
from trends.collectors.runner import collect_sources
from trends.config import load_digests, load_sources
from trends.domain.ids import slugify
from trends.domain.models import (
    Article,
    CurrencyRate,
    DailyDigest,
    DailyPicture,
    DigestEvent,
    DigestProfile,
)
from trends.pipeline.dedupe import dedupe_articles
from trends.pipeline.event_builder import build_event, partition_articles
from trends.pipeline.event_lifecycle import (
    audit_feed,
    hydrate_events,
    load_recent_catalog,
    merge_with_recent,
    rank_events,
)
from trends.pipeline.normalize import normalize_articles
from trends.pipeline.rank import cluster_score
from trends.pipeline.select import select_for_digest
from trends.storage.daily_store import DailyStore


def _rule_key(value: str) -> str:
    return slugify(value).replace("-", "_")


def _minimum_sources_for_event(
    profile: DigestProfile, event: DigestEvent
) -> int:
    allowed = {
        _rule_key(value) for value in profile.sources.allow_single_source_for
    }
    event_types = {_rule_key(event.category)}
    if event.identity:
        event_types.add(_rule_key(event.identity.event_type))
    return 1 if allowed & event_types else profile.sources.min_independent_sources


def _error(stage: str, error: Exception) -> str:
    detail = " ".join(str(error).split())[:220]
    return f"{stage}:{type(error).__name__}:{detail}" if detail else (
        f"{stage}:{type(error).__name__}"
    )


def _currency_rates(root: Path) -> list[CurrencyRate]:
    path = root / "data/currency_history.json"
    if not path.exists():
        return []
    history = json.loads(path.read_text(encoding="utf-8"))
    dates = sorted(history)
    if not dates:
        return []
    current = history[dates[-1]]
    previous = history[dates[-2]] if len(dates) > 1 else {}
    result = []
    for source_key, pair in (
        ("USDRUB", "USD/RUB"),
        ("EURRUB", "EUR/RUB"),
        ("CNYRUB", "CNY/RUB"),
    ):
        value = current.get(source_key)
        if value is None:
            continue
        old = previous.get(source_key)
        change = round((value - old) / old * 100, 2) if old else None
        result.append(CurrencyRate(pair=pair, value=value, change_pct=change))
    return result


def _source_history(root: Path, digest_id: str) -> dict[str, list[int]]:
    path = root / "data/digests" / digest_id / "source-history.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        source["source_id"]: [
            release["accepted"] for release in source.get("releases", [])
        ][-6:]
        for source in payload.get("sources", [])
    }


def _rank_clusters(
    clusters: list[list[Article]], profile: DigestProfile
) -> list[list[Article]]:
    return sorted(
        clusters,
        key=lambda cluster: cluster_score(
            cluster,
            profile,
            min(10, 5 + len({article.source_id for article in cluster})),
        ),
        reverse=True,
    )


async def run_production(root: Path) -> list[Path]:
    started = datetime.now(UTC)
    source_configs = load_sources(root / "config/sources")
    raw_articles, source_runs = await collect_sources(source_configs)
    normalized = normalize_articles(raw_articles)
    articles, local_dedupe = dedupe_articles(normalized)
    profiles = [
        profile
        for profile in load_digests(root / "config/digests")
        if profile.enabled
    ]
    google_api_key = os.getenv("GOOGLE_API_KEY")
    provider = GeminiProvider(google_api_key) if google_api_key else None
    ai = (
        EventSynthesisService(
            provider,
            translation_api_key=google_api_key,
        )
        if provider
        else None
    )
    dedupe_ai = DedupeService(provider) if provider else None
    store = DailyStore(root / "data/digests")
    written: list[Path] = []
    run_report: dict[str, object] = {
        "started_at": started.isoformat(),
        "raw_articles": len(raw_articles),
        "normalized_articles": len(normalized),
        "dedupe": local_dedupe.to_dict(),
        "sources": [item.model_dump(mode="json") for item in source_runs],
        "digests": {},
    }

    for profile in profiles:
        selected = select_for_digest(articles, profile)
        today, recent_events, archived_articles, catalog_errors = (
            load_recent_catalog(
                root,
                profile.id,
                started,
                profile.dedupe.lookback_hours,
            )
        )
        article_catalog = {
            **archived_articles,
            **{article.id: article for article in selected},
        }
        metrics: dict[str, object] = {
            "degraded": bool(catalog_errors),
            "errors": list(catalog_errors),
            "generation_model": provider.model if provider else None,
            "embedding_model": provider.embedding_model if provider else None,
            "thresholds": profile.dedupe.model_dump(mode="json"),
            "semantic_candidate_pairs": 0,
            "candidate_bundles": 0,
            "ai_partitions": 0,
            "ai_splits": 0,
            "fallback_events": 0,
            "reused_event_ids": 0,
            "article_overlap_merges": 0,
            "final_audit_merges": 0,
        }
        clusters = await partition_articles(
            selected,
            profile,
            provider,
            dedupe_ai,
            metrics,
        )
        clusters = _rank_clusters(clusters, profile)
        synthesis_limit = profile.output.max_events * 2
        candidate_clusters = clusters[:synthesis_limit]
        metrics["candidate_clusters"] = len(clusters)
        metrics["synthesized_clusters"] = len(candidate_clusters)
        metrics["skipped_low_rank_clusters"] = max(
            0, len(clusters) - len(candidate_clusters)
        )

        events: list[DigestEvent] = []
        quarantine: list[dict[str, object]] = []
        for cluster in candidate_clusters:
            independent_sources = len({item.source_id for item in cluster})
            try:
                event = await build_event(
                    profile,
                    cluster,
                    started,
                    ai,
                    minimum_sources=1,
                )
            except Exception as error:
                metrics["degraded"] = True
                metrics["fallback_events"] = int(
                    metrics["fallback_events"]
                ) + 1
                metrics.setdefault("errors", []).append(
                    _error("synthesis", error)
                )
                event = await build_event(profile, cluster, started, None)

            minimum_sources = _minimum_sources_for_event(profile, event)
            if independent_sources < minimum_sources:
                quarantine.append(
                    {
                        "reason": "insufficient_sources",
                        "required": minimum_sources,
                        "article_ids": [item.id for item in cluster],
                    }
                )
                continue
            events.append(event)

        events = await merge_with_recent(
            events,
            recent_events,
            today,
            profile,
            provider,
            dedupe_ai,
            metrics,
        )
        ranked = rank_events(events, article_catalog, profile)
        ranked = await audit_feed(
            ranked,
            article_catalog,
            profile,
            started,
            ai,
            dedupe_ai,
            metrics,
        )
        ranked, orphaned = hydrate_events(ranked, article_catalog)
        metrics["orphaned_events"] = orphaned
        ranked = rank_events(ranked, article_catalog, profile)

        visible_events = ranked[: profile.output.max_events]
        accepted_ids = {
            article_id
            for event in visible_events
            for article_id in event.article_ids
        }
        current_ids = {article.id for article in selected}
        current_order = [
            article.id for article in selected if article.id in accepted_ids
        ]
        archived_order = [
            article.id
            for article in sorted(
                archived_articles.values(),
                key=lambda item: (
                    item.published_at or item.collected_at,
                    item.id,
                ),
                reverse=True,
            )
            if article.id in accepted_ids and article.id not in current_ids
        ]
        digest_articles = [
            article_catalog[article_id]
            for article_id in [*current_order, *archived_order]
        ]

        by_source_events: dict[str, int] = {}
        for event in visible_events:
            represented = {
                article.source_id
                for article in digest_articles
                if article.id in event.article_ids
            }
            for source_id in represented:
                by_source_events[source_id] = (
                    by_source_events.get(source_id, 0) + 1
                )
        digest_sources = []
        previous_history = _source_history(root, profile.id)
        current_accepted_ids = accepted_ids & current_ids
        for run in source_runs:
            accepted = sum(
                1
                for article in selected
                if article.source_id == run.source_id
                and article.id in current_accepted_ids
            )
            digest_sources.append(
                run.model_copy(
                    update={
                        "accepted": accepted,
                        "represented_events": by_source_events.get(
                            run.source_id, 0
                        ),
                        "history": [
                            *previous_history.get(run.source_id, []),
                            accepted,
                        ][-7:],
                    }
                )
            )

        body = (
            f"В выпуске «{profile.title}» отобрано "
            f"{len(visible_events)} подтвержденных событий. "
            f"Редакционный фильтр обработал {len(selected)} материалов, "
            f"объединил {metrics['article_overlap_merges']} повторных карточек "
            f"и исключил {len(quarantine)} неподтвержденных кластеров."
        )
        digest = DailyDigest(
            digest_id=profile.id,
            date=started.date(),
            generated_at=started,
            daily_picture=DailyPicture(body=body),
            currencies=_currency_rates(root) if profile.id == "world" else [],
            sources=digest_sources,
            articles=digest_articles,
            events=visible_events,
        )
        if digest.events or today is None:
            written.append(store.write(digest))
        metrics["dedupe_degraded"] = bool(metrics["degraded"])
        run_report["digests"][profile.id] = {
            "selected": len(selected),
            "published": len(digest.events),
            "quarantined": quarantine,
            "dedupe": metrics,
        }

    report_path = (
        root
        / "data/runs"
        / started.strftime("%Y/%m/%d")
        / f"{started.strftime('%H%M%S')}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(run_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return written
