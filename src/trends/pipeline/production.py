from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from trends.ai.gemini import GeminiProvider
from trends.ai.service import EventSynthesisService
from trends.collectors.runner import collect_sources
from trends.config import load_digests, load_sources
from trends.domain.enums import EventStatus
from trends.domain.ids import slugify
from trends.domain.models import (
    CurrencyRate,
    DailyDigest,
    DailyPicture,
    DigestEvent,
    Fact,
)
from trends.pipeline.cluster import cluster_articles
from trends.pipeline.dedupe import exact_dedupe
from trends.pipeline.merge import merge_events
from trends.pipeline.normalize import normalize_articles
from trends.pipeline.rank import cluster_score
from trends.pipeline.select import select_for_digest
from trends.storage.daily_store import DailyStore

_REAL_ARTICLE_ID = re.compile(r"^[0-9a-f]{20}$")


def _event_id(digest_id: str, title: str) -> str:
    fingerprint = " ".join(sorted(set(title.casefold().split())))
    return f"{digest_id}-{hashlib.sha256(fingerprint.encode()).hexdigest()[:16]}"


def _fallback_text(value: str, minimum: int) -> str:
    suffix = " Сводка создана автоматически из доступных заголовков и описаний; дополнительные сведения появятся после подтверждения независимыми источниками."
    result = value.strip()
    if len(result) < minimum:
        result = f"{result}{suffix}"
    return result


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
    for source_key, pair in (("USDRUB", "USD/RUB"), ("EURRUB", "EUR/RUB"), ("CNYRUB", "CNY/RUB")):
        value = current.get(source_key)
        if value is None:
            continue
        old = previous.get(source_key)
        change = round((value - old) / old * 100, 2) if old else None
        result.append(CurrencyRate(pair=pair, value=value, change_pct=change))
    return result


def _load_existing(root: Path, digest_id: str, day: str) -> DailyDigest | None:
    path = root / "data/digests" / digest_id / "days" / day[:4] / day[5:7] / f"{day}.json"
    if not path.exists():
        return None
    return DailyDigest.model_validate_json(path.read_text(encoding="utf-8"))


def _source_history(root: Path, digest_id: str) -> dict[str, list[int]]:
    path = root / "data/digests" / digest_id / "source-history.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        source["source_id"]: [release["accepted"] for release in source.get("releases", [])][-6:]
        for source in payload.get("sources", [])
    }


async def run_production(root: Path) -> list[Path]:
    started = datetime.now(UTC)
    raw_articles, source_runs = await collect_sources(load_sources(root / "config/sources"))
    articles = exact_dedupe(normalize_articles(raw_articles))
    profiles = [profile for profile in load_digests(root / "config/digests") if profile.enabled]
    google_api_key = os.getenv("GOOGLE_API_KEY")
    provider = GeminiProvider(google_api_key) if google_api_key else None
    ai = EventSynthesisService(provider, translation_api_key=google_api_key) if provider else None
    store = DailyStore(root / "data/digests")
    written: list[Path] = []
    run_report: dict[str, object] = {
        "started_at": started.isoformat(),
        "raw_articles": len(raw_articles),
        "normalized_articles": len(articles),
        "sources": [item.model_dump(mode="json") for item in source_runs],
        "digests": {},
    }

    for profile in profiles:
        selected = select_for_digest(articles, profile)
        clusters = cluster_articles(selected)
        events: list[tuple[float, DigestEvent]] = []
        quarantine: list[dict[str, object]] = []
        for cluster in clusters:
            independent_sources = len({item.source_id for item in cluster})
            minimum = profile.sources.min_independent_sources
            if independent_sources < minimum:
                quarantine.append({"reason": "insufficient_sources", "article_ids": [item.id for item in cluster]})
                continue
            primary = cluster[0]
            real_ids = {item.id for item in cluster}
            title = primary.title
            brief = _fallback_text(primary.excerpt or primary.title, 220)
            context = _fallback_text(primary.excerpt or primary.title, 220)
            why = _fallback_text(f"Событие затрагивает тему «{profile.title}».", 170)
            category = primary.topic_hints[-1] if primary.topic_hints else "news"
            importance = min(10, 5 + independent_sources)
            article_ids = [item.id for item in cluster]
            facts = [Fact(text=primary.excerpt or primary.title, article_ids=[primary.id])]
            status = EventStatus.NEW
            try:
                if ai:
                    synthesis = await ai.synthesize(cluster, minimum_sources=minimum)
                    title = synthesis.title
                    brief = synthesis.brief
                    context = synthesis.context
                    why = synthesis.why_it_matters
                    category = synthesis.category
                    importance = synthesis.impact
                    # Only accept AI article_ids that reference real cluster articles.
                    valid_ai_ids = [aid for aid in synthesis.article_ids if aid in real_ids]
                    article_ids = valid_ai_ids if valid_ai_ids else article_ids
                    facts = [
                        Fact(
                            text=fact.text,
                            article_ids=[aid for aid in fact.article_ids if aid in real_ids] or article_ids,
                        )
                        for fact in synthesis.facts
                    ]
                    try:
                        status = EventStatus(synthesis.status)
                    except ValueError:
                        status = EventStatus.NEW
            except Exception as error:
                quarantine.append({
                    "reason": type(error).__name__,
                    "error": str(error)[:300],
                    "article_ids": [item.id for item in cluster],
                })
                continue

            event = DigestEvent(
                id=_event_id(profile.id, title),
                slug=slugify(title),
                title=title,
                brief=brief,
                context=context,
                why_it_matters=why,
                importance=importance,
                status=status,
                category=category,
                article_ids=article_ids,
                facts=facts,
                first_seen_at=min((item.published_at or item.collected_at) for item in cluster),
                updated_at=started,
            )
            events.append((cluster_score(cluster, profile, importance), event))

        ranked = [event for _, event in sorted(events, key=lambda item: item[0], reverse=True)]
        existing = _load_existing(root, profile.id, str(started.date()))
        if existing:
            # Drop events whose article IDs were fabricated by AI instead of
            # taken from the real cluster. Real IDs are 20-char hex strings.
            clean_existing = [
                e for e in existing.events
                if any(_REAL_ARTICLE_ID.match(aid) for aid in e.article_ids)
            ]
            ranked = merge_events(clean_existing, ranked)

        accepted_ids = {article_id for event in ranked for article_id in event.article_ids}
        digest_articles = [article for article in selected if article.id in accepted_ids]
        by_source_events: dict[str, int] = {}
        for event in ranked:
            represented = {article.source_id for article in digest_articles if article.id in event.article_ids}
            for source_id in represented:
                by_source_events[source_id] = by_source_events.get(source_id, 0) + 1
        digest_sources = []
        previous_history = _source_history(root, profile.id)
        for run in source_runs:
            accepted = sum(1 for article in digest_articles if article.source_id == run.source_id)
            digest_sources.append(run.model_copy(update={
                "accepted": accepted,
                "represented_events": by_source_events.get(run.source_id, 0),
                "history": [*previous_history.get(run.source_id, []), accepted][-7:],
            }))

        body = (
            f"В выпуске «{profile.title}» отобрано {len(ranked)} подтвержденных событий. "
            f"Редакционный фильтр обработал {len(selected)} тематических материалов "
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
            events=ranked[: profile.output.max_events],
        )
        # Do not replace a healthy existing release with an empty transient run.
        if digest.events or existing is None:
            written.append(store.write(digest))
        run_report["digests"][profile.id] = {
            "selected": len(selected),
            "published": len(digest.events),
            "quarantined": quarantine,
        }

    report_path = root / "data/runs" / started.strftime("%Y/%m/%d") / f"{started.strftime('%H%M%S')}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(run_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return written
