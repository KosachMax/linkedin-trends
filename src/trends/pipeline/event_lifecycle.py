from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from rapidfuzz.fuzz import token_set_ratio

from trends.ai.dedupe_service import DedupeService
from trends.ai.gemini import GeminiProvider
from trends.ai.schemas import EventRelationDecision
from trends.ai.service import EventSynthesisService
from trends.domain.enums import EventStatus
from trends.domain.ids import slugify
from trends.domain.models import (
    Article,
    DailyDigest,
    DigestEvent,
    DigestProfile,
    EventIdentity,
    Fact,
)

from .merge import (
    assert_unique_article_ownership,
    collapse_article_overlaps,
    combine_duplicate_events,
    merge_event_pair,
)
from .rank import cluster_score
from .semantic import event_embedding_text, nearest_event_pairs


def _error(stage: str, error: Exception) -> str:
    detail = " ".join(str(error).split())[:180]
    return f"{stage}:{type(error).__name__}:{detail}" if detail else (
        f"{stage}:{type(error).__name__}"
    )


def _obvious_title_duplicate_groups(
    events: list[DigestEvent],
    lookback_hours: int,
) -> list[list[str]]:
    """Find near-identical generated cards as a deterministic audit safety net."""
    parent = list(range(len(events)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index, left in enumerate(events):
        for right_index in range(left_index + 1, len(events)):
            right = events[right_index]
            age_hours = abs(
                (left.first_seen_at - right.first_seen_at).total_seconds()
            ) / 3600
            if age_hours > lookback_hours:
                continue
            if token_set_ratio(left.title, right.title) < 90:
                continue
            if left.identity and right.identity:
                if left.identity.event_type != right.identity.event_type:
                    continue
                left_entities = {
                    item.casefold() for item in left.identity.primary_entities
                }
                right_entities = {
                    item.casefold() for item in right.identity.primary_entities
                }
                if left_entities and right_entities and not (
                    left_entities & right_entities
                ):
                    continue
            union(left_index, right_index)

    grouped: dict[int, list[str]] = {}
    for index, event in enumerate(events):
        grouped.setdefault(find(index), []).append(event.id)
    return [event_ids for event_ids in grouped.values() if len(event_ids) > 1]


def _combine_group_ids(groups: list[list[str]]) -> list[list[str]]:
    """Union overlapping AI and deterministic duplicate groups."""
    parent: dict[str, str] = {}

    def find(event_id: str) -> str:
        parent.setdefault(event_id, event_id)
        while parent[event_id] != event_id:
            parent[event_id] = parent[parent[event_id]]
            event_id = parent[event_id]
        return event_id

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for group in groups:
        if not group:
            continue
        for event_id in group:
            find(event_id)
        for event_id in group[1:]:
            union(group[0], event_id)

    components: dict[str, list[str]] = {}
    for event_id in parent:
        components.setdefault(find(event_id), []).append(event_id)
    return [event_ids for event_ids in components.values() if len(event_ids) > 1]


def _digest_path(root: Path, digest_id: str, day: str) -> Path:
    return (
        root
        / "data/digests"
        / digest_id
        / "days"
        / day[:4]
        / day[5:7]
        / f"{day}.json"
    )


def _load_digest(path: Path) -> DailyDigest | None:
    if not path.exists():
        return None
    return DailyDigest.model_validate_json(path.read_text(encoding="utf-8"))


def load_recent_catalog(
    root: Path,
    digest_id: str,
    started: datetime,
    lookback_hours: int,
) -> tuple[DailyDigest | None, list[DigestEvent], dict[str, Article], list[str]]:
    today: DailyDigest | None = None
    latest_events: dict[str, DigestEvent] = {}
    articles: dict[str, Article] = {}
    errors: list[str] = []
    day_count = math.ceil(lookback_hours / 24)
    for offset in range(day_count + 1):
        day = (started.date() - timedelta(days=offset)).isoformat()
        path = _digest_path(root, digest_id, day)
        try:
            digest = _load_digest(path)
        except (ValueError, OSError, json.JSONDecodeError) as error:
            errors.append(_error(path.name, error))
            continue
        if digest is None:
            continue
        if offset == 0:
            today = digest
        articles.update({article.id: article for article in digest.articles})
        for event in digest.events:
            age_hours = (started - event.updated_at).total_seconds() / 3600
            if age_hours > lookback_hours:
                continue
            previous = latest_events.get(event.id)
            if previous is None or event.updated_at > previous.updated_at:
                latest_events[event.id] = event
    return today, list(latest_events.values()), articles, errors


async def merge_with_recent(
    incoming: list[DigestEvent],
    recent: list[DigestEvent],
    today: DailyDigest | None,
    profile: DigestProfile,
    provider: GeminiProvider | None,
    dedupe_ai: DedupeService | None,
    metrics: dict[str, object],
) -> list[DigestEvent]:
    recent, overlap_merges = collapse_article_overlaps(recent)
    metrics["article_overlap_merges"] = int(
        metrics.get("article_overlap_merges", 0)
    ) + overlap_merges
    recent_by_id = {event.id: event for event in recent}
    merged: dict[str, DigestEvent] = {}
    order: list[str] = []
    unmatched: list[DigestEvent] = []
    matched_old_ids: set[str] = set()

    def put(event: DigestEvent) -> None:
        if event.id not in merged:
            order.append(event.id)
            merged[event.id] = event
        else:
            merged[event.id] = merge_event_pair(merged[event.id], event)

    for candidate in incoming:
        old = recent_by_id.get(candidate.id)
        if old is None:
            candidate_articles = set(candidate.article_ids)
            old = next(
                (
                    event
                    for event in recent
                    if event.id not in matched_old_ids
                    and candidate_articles & set(event.article_ids)
                ),
                None,
            )
        if old:
            put(merge_event_pair(old, candidate))
            matched_old_ids.add(old.id)
            metrics["reused_event_ids"] = int(
                metrics.get("reused_event_ids", 0)
            ) + 1
        else:
            unmatched.append(candidate)

    available_recent = [
        event for event in recent if event.id not in matched_old_ids
    ]
    decisions: list[EventRelationDecision] = []
    if unmatched and available_recent and provider and dedupe_ai:
        try:
            incoming_vectors = await provider.embed(
                [event_embedding_text(event) for event in unmatched]
            )
            recent_vectors = await provider.embed(
                [event_embedding_text(event) for event in available_recent]
            )
            pairs = nearest_event_pairs(
                unmatched,
                available_recent,
                incoming_vectors,
                recent_vectors,
                profile.dedupe,
            )
            metrics["event_candidate_pairs"] = len(pairs)
            for start in range(0, len(pairs), 20):
                batch = await dedupe_ai.classify_event_pairs(
                    pairs[start : start + 20]
                )
                decisions.extend(batch.decisions)
        except Exception as error:
            metrics["degraded"] = True
            metrics.setdefault("errors", []).append(_error("event_match", error))

    decisions_by_candidate: dict[str, list[EventRelationDecision]] = {}
    for decision in decisions:
        decisions_by_candidate.setdefault(decision.left_event_id, []).append(
            decision
        )

    for candidate in unmatched:
        eligible = [
            decision
            for decision in decisions_by_candidate.get(candidate.id, [])
            if decision.relation in {"same_event", "update_of"}
            and decision.confidence >= profile.dedupe.event_match_confidence
        ]
        if eligible:
            decision = max(eligible, key=lambda item: item.confidence)
            old = recent_by_id[decision.right_event_id]
            put(merge_event_pair(old, candidate))
            matched_old_ids.add(old.id)
            metrics["reused_event_ids"] = int(
                metrics.get("reused_event_ids", 0)
            ) + 1
        else:
            put(candidate)

    if today:
        for old in today.events:
            if old.id not in matched_old_ids and old.id not in merged:
                put(old)

    result = [merged[event_id] for event_id in order]
    result, overlap_merges = collapse_article_overlaps(result)
    metrics["article_overlap_merges"] = int(
        metrics.get("article_overlap_merges", 0)
    ) + overlap_merges
    assert_unique_article_ownership(result)
    return result


async def _resynthesize_duplicate_group(
    events: list[DigestEvent],
    article_catalog: dict[str, Article],
    started: datetime,
    ai: EventSynthesisService | None,
    metrics: dict[str, object],
) -> DigestEvent:
    combined = combine_duplicate_events(events)
    articles = [
        article_catalog[article_id]
        for article_id in combined.article_ids
        if article_id in article_catalog
    ]
    if not ai or not articles:
        return combined
    try:
        synthesis = await ai.synthesize(articles, minimum_sources=1)
        return DigestEvent(
            id=combined.id,
            slug=slugify(synthesis.title),
            title=synthesis.title,
            brief=synthesis.brief,
            context=synthesis.context,
            why_it_matters=synthesis.why_it_matters,
            importance=synthesis.impact,
            status=EventStatus(synthesis.status),
            category=synthesis.category,
            article_ids=[article.id for article in articles],
            facts=[
                Fact(text=fact.text, article_ids=fact.article_ids)
                for fact in synthesis.facts
            ],
            updates=combined.updates,
            identity=EventIdentity.model_validate(
                synthesis.identity.model_dump()
            ),
            first_seen_at=combined.first_seen_at,
            updated_at=started,
        )
    except Exception as error:
        metrics["degraded"] = True
        metrics.setdefault("errors", []).append(
            _error("audit_resynthesis", error)
        )
        return combined


async def audit_feed(
    events: list[DigestEvent],
    article_catalog: dict[str, Article],
    profile: DigestProfile,
    started: datetime,
    ai: EventSynthesisService | None,
    dedupe_ai: DedupeService | None,
    metrics: dict[str, object],
) -> list[DigestEvent]:
    events, overlap_merges = collapse_article_overlaps(events)
    metrics["article_overlap_merges"] = int(
        metrics.get("article_overlap_merges", 0)
    ) + overlap_merges
    if not dedupe_ai or len(events) < 2:
        assert_unique_article_ownership(events)
        return events

    window_size = min(len(events), profile.output.max_events * 2)
    local_groups = _obvious_title_duplicate_groups(
        events[:window_size], profile.dedupe.lookback_hours
    )
    metrics["local_title_duplicate_groups"] = len(local_groups)
    ai_groups: list[list[str]] = []
    try:
        audit = await dedupe_ai.audit_feed(events[:window_size])
        ai_groups = [
            group.event_ids
            for group in audit.duplicate_groups
            if group.confidence >= profile.dedupe.final_audit_confidence
        ]
    except Exception as error:
        metrics["degraded"] = True
        metrics.setdefault("errors", []).append(_error("feed_audit", error))
    groups = _combine_group_ids([*ai_groups, *local_groups])
    if not groups:
        assert_unique_article_ownership(events)
        return events

    by_id = {event.id: event for event in events}
    replacements: dict[str, DigestEvent] = {}
    member_to_keeper: dict[str, str] = {}
    for group in groups:
        grouped_events = [by_id[event_id] for event_id in group]
        replacement = await _resynthesize_duplicate_group(
            grouped_events,
            article_catalog,
            started,
            ai,
            metrics,
        )
        keeper = min(
            group,
            key=lambda event_id: (by_id[event_id].first_seen_at, event_id),
        )
        replacement.id = keeper
        replacements[keeper] = replacement
        for event_id in group:
            member_to_keeper[event_id] = keeper

    result = []
    emitted: set[str] = set()
    for event in events:
        keeper = member_to_keeper.get(event.id)
        if keeper is None:
            result.append(event)
        elif keeper not in emitted:
            result.append(replacements[keeper])
            emitted.add(keeper)
    metrics["final_audit_merges"] = sum(
        len(group) - 1 for group in groups
    )
    result, overlap_merges = collapse_article_overlaps(result)
    metrics["article_overlap_merges"] = int(
        metrics.get("article_overlap_merges", 0)
    ) + overlap_merges
    assert_unique_article_ownership(result)
    return result


def hydrate_events(
    events: list[DigestEvent],
    articles: dict[str, Article],
) -> tuple[list[DigestEvent], int]:
    hydrated: list[DigestEvent] = []
    orphaned = 0
    for event in events:
        known_ids = [
            article_id
            for article_id in event.article_ids
            if article_id in articles
        ]
        if not known_ids:
            orphaned += 1
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
                    ],
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
    hydrated, _ = collapse_article_overlaps(hydrated)
    assert_unique_article_ownership(hydrated)
    return hydrated, orphaned


def rank_events(
    events: list[DigestEvent],
    article_catalog: dict[str, Article],
    profile: DigestProfile,
) -> list[DigestEvent]:
    def score(event: DigestEvent) -> float:
        articles = [
            article_catalog[article_id]
            for article_id in event.article_ids
            if article_id in article_catalog
        ]
        return cluster_score(articles, profile, event.importance) if articles else 0.0

    return sorted(
        events,
        key=lambda event: (score(event), event.importance),
        reverse=True,
    )
