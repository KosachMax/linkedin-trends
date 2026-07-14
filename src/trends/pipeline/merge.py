from __future__ import annotations

from copy import deepcopy

from trends.domain.enums import EventStatus
from trends.domain.models import DigestEvent, EventUpdate, Fact


def _ordered_union(left: list[str], right: list[str]) -> list[str]:
    return list(dict.fromkeys([*left, *right]))


def merge_event_pair(old: DigestEvent, candidate: DigestEvent) -> DigestEvent:
    """Attach a new observation to one stable event without losing provenance."""
    result = deepcopy(candidate)
    result.id = old.id
    result.first_seen_at = min(old.first_seen_at, candidate.first_seen_at)
    result.article_ids = _ordered_union(old.article_ids, candidate.article_ids)
    result.updates = list(old.updates)
    result.identity = candidate.identity or old.identity

    old_facts = {fact.text.casefold().strip() for fact in old.facts}
    new_facts = [
        fact
        for fact in candidate.facts
        if fact.text.casefold().strip() not in old_facts
    ]
    result.facts = [*old.facts, *new_facts]
    material = (
        bool(new_facts)
        or candidate.status != old.status
        or abs(candidate.importance - old.importance) >= 2
    )
    if material:
        result.status = (
            EventStatus.UPDATED
            if candidate.status == EventStatus.NEW
            else candidate.status
        )
        if new_facts:
            summary = " ".join(fact.text for fact in new_facts[:2])[:500]
        elif candidate.status != old.status:
            summary = f"Статус события изменён на «{result.status.value}»."
        else:
            summary = "Обновлена редакционная оценка важности события."
        result.updates.append(
            EventUpdate(
                at=candidate.updated_at,
                summary=summary,
                article_ids=candidate.article_ids,
            )
        )
        return result

    stable = deepcopy(old)
    stable.article_ids = result.article_ids
    stable.first_seen_at = result.first_seen_at
    stable.identity = result.identity
    return stable


def combine_duplicate_events(events: list[DigestEvent]) -> DigestEvent:
    """Combine duplicate cards without dropping facts, updates, or articles."""
    if not events:
        raise ValueError("at least one event is required")
    earliest = min(events, key=lambda event: (event.first_seen_at, event.id))
    primary = max(events, key=lambda event: (event.importance, event.updated_at))
    result = deepcopy(primary)
    result.id = earliest.id
    result.first_seen_at = earliest.first_seen_at
    result.article_ids = list(
        dict.fromkeys(
            article_id
            for event in events
            for article_id in event.article_ids
        )
    )
    facts: list[Fact] = []
    seen_facts: set[str] = set()
    for event in events:
        for fact in event.facts:
            key = fact.text.casefold().strip()
            if key not in seen_facts:
                seen_facts.add(key)
                facts.append(fact)
    result.facts = facts
    result.updates = sorted(
        [update for event in events for update in event.updates],
        key=lambda update: update.at,
    )
    return result


def collapse_article_overlaps(
    events: list[DigestEvent],
) -> tuple[list[DigestEvent], int]:
    """Merge connected components that reuse any article ID.

    A collector assigns every article to one event per run. Therefore the same
    article appearing in two cards after an intraday merge is deterministic
    evidence of duplicate event identity, not merely semantic similarity.
    """
    if len(events) < 2:
        return events, 0

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

    owner: dict[str, int] = {}
    for index, event in enumerate(events):
        for article_id in event.article_ids:
            previous = owner.setdefault(article_id, index)
            if previous != index:
                union(previous, index)

    groups: dict[int, list[DigestEvent]] = {}
    order: list[int] = []
    for index, event in enumerate(events):
        root = find(index)
        if root not in groups:
            groups[root] = []
            order.append(root)
        groups[root].append(event)

    result = [
        group[0] if len(group) == 1 else combine_duplicate_events(group)
        for group in (groups[root] for root in order)
    ]
    return result, len(events) - len(result)


def assert_unique_article_ownership(events: list[DigestEvent]) -> None:
    owner: dict[str, str] = {}
    for event in events:
        for article_id in event.article_ids:
            previous = owner.setdefault(article_id, event.id)
            if previous != event.id:
                raise ValueError(
                    f"article {article_id} belongs to both {previous} and {event.id}"
                )


def merge_events(
    existing: list[DigestEvent], incoming: list[DigestEvent]
) -> list[DigestEvent]:
    """Backward-compatible intraday merge with deterministic overlap collapse."""
    previous = {event.id: event for event in existing}
    merged: list[DigestEvent] = []
    for candidate in incoming:
        old = previous.pop(candidate.id, None)
        if old is None:
            overlapping_id = next(
                (
                    event_id
                    for event_id, event in previous.items()
                    if set(event.article_ids) & set(candidate.article_ids)
                ),
                None,
            )
            old = previous.pop(overlapping_id) if overlapping_id else None
        merged.append(merge_event_pair(old, candidate) if old else candidate)
    merged.extend(previous.values())
    collapsed, _ = collapse_article_overlaps(merged)
    return sorted(
        collapsed,
        key=lambda event: (-event.importance, event.first_seen_at),
    )
