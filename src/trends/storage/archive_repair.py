from __future__ import annotations

from datetime import date
from pathlib import Path

from trends.domain.models import DailyDigest, DailyPicture, DigestEvent
from trends.pipeline.merge import (
    collapse_article_overlaps,
    combine_duplicate_events,
)

from .daily_store import DailyStore


def _archive_path(root: Path, digest_id: str, day: date) -> Path:
    return (
        root
        / "data/digests"
        / digest_id
        / "days"
        / day.strftime("%Y/%m")
        / f"{day}.json"
    )


def _merge_explicit_groups(
    digest: DailyDigest, groups: list[list[str]]
) -> list[DigestEvent]:
    by_id = {event.id: event for event in digest.events}
    index_by_id = {event.id: index for index, event in enumerate(digest.events)}
    used: set[str] = set()
    replacements: dict[int, DigestEvent] = {}

    for group in groups:
        if len(group) < 2 or len(group) != len(set(group)):
            raise ValueError("every merge group must contain at least two unique IDs")
        unknown = set(group) - by_id.keys()
        if unknown:
            raise ValueError(f"merge group contains unknown event IDs: {sorted(unknown)}")
        repeated = set(group) & used
        if repeated:
            raise ValueError(f"events occur in multiple merge groups: {sorted(repeated)}")
        used.update(group)
        first_index = min(index_by_id[event_id] for event_id in group)
        replacements[first_index] = combine_duplicate_events(
            [by_id[event_id] for event_id in group]
        )

    return [
        replacements.get(index, event)
        for index, event in enumerate(digest.events)
        if event.id not in used or index in replacements
    ]


def _remove_orphaned_references(
    events: list[DigestEvent], known_articles: set[str]
) -> tuple[list[DigestEvent], int, int]:
    hydrated: list[DigestEvent] = []
    orphaned_events = 0
    dropped_references = 0
    for event in events:
        known_ids = [
            article_id
            for article_id in event.article_ids
            if article_id in known_articles
        ]
        dropped_references += len(event.article_ids) - len(known_ids)
        if not known_ids:
            orphaned_events += 1
            continue
        known = set(known_ids)
        facts = []
        for fact in event.facts:
            fact_ids = [
                article_id
                for article_id in fact.article_ids
                if article_id in known
            ]
            if fact_ids:
                facts.append(fact.model_copy(update={"article_ids": fact_ids}))
        updates = [
            update.model_copy(
                update={
                    "article_ids": [
                        article_id
                        for article_id in update.article_ids
                        if article_id in known
                    ]
                }
            )
            for update in event.updates
        ]
        hydrated.append(
            event.model_copy(
                update={
                    "article_ids": known_ids,
                    "facts": facts,
                    "updates": updates,
                }
            )
        )
    return hydrated, orphaned_events, dropped_references


def repair_archive(
    root: Path,
    digest_id: str,
    day: date,
    merge_groups: list[list[str]],
) -> dict[str, object]:
    path = _archive_path(root, digest_id, day)
    if not path.exists():
        raise FileNotFoundError(path)
    digest = DailyDigest.model_validate_json(path.read_text(encoding="utf-8"))
    if digest.digest_id != digest_id or digest.date != day:
        raise ValueError("archive identity does not match requested digest and date")

    before = len(digest.events)
    events = _merge_explicit_groups(digest, merge_groups)
    events, orphaned_events, dropped_references = _remove_orphaned_references(
        events,
        {article.id for article in digest.articles},
    )
    events, overlap_merges = collapse_article_overlaps(events)
    accepted_ids = {
        article_id for event in events for article_id in event.article_ids
    }
    articles = [
        article for article in digest.articles if article.id in accepted_ids
    ]
    article_by_id = {article.id: article for article in articles}
    sources = []
    for source in digest.sources:
        accepted = sum(
            article.source_id == source.source_id for article in articles
        )
        represented = sum(
            any(
                article_by_id[article_id].source_id == source.source_id
                for article_id in event.article_ids
            )
            for event in events
        )
        sources.append(
            source.model_copy(
                update={
                    "accepted": accepted,
                    "represented_events": represented,
                }
            )
        )

    repaired = digest.model_copy(
        update={
            "schema_version": 2,
            "daily_picture": DailyPicture(
                body=(
                    "После архивной дедупликации в выпуске за "
                    f"{day.strftime('%d.%m.%Y')} "
                    f"осталось {len(events)} событий. Все материалы, факты и "
                    "ссылки на источники сохранены внутри объединённых карточек."
                )
            ),
            "sources": sources,
            "articles": articles,
            "events": events,
        }
    )
    written = DailyStore(root / "data/digests").rewrite_archive(repaired)
    return {
        "path": str(written),
        "events_before": before,
        "events_after": len(events),
        "explicit_merges": sum(len(group) - 1 for group in merge_groups),
        "overlap_merges": overlap_merges,
        "orphaned_events": orphaned_events,
        "dropped_article_references": dropped_references,
        "articles_after": len(articles),
    }
