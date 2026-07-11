from copy import deepcopy

from trends.domain.enums import EventStatus
from trends.domain.models import DigestEvent, EventUpdate


def merge_events(existing: list[DigestEvent], incoming: list[DigestEvent]) -> list[DigestEvent]:
    """Merge an intraday run without creating noisy updates for source-only changes."""
    previous = {event.id: event for event in existing}
    merged: list[DigestEvent] = []
    for candidate in incoming:
        old = previous.pop(candidate.id, None)
        if old is None:
            merged.append(candidate)
            continue

        result = deepcopy(candidate)
        result.first_seen_at = old.first_seen_at
        result.updates = list(old.updates)
        old_facts = {fact.text for fact in old.facts}
        new_facts = [fact for fact in candidate.facts if fact.text not in old_facts]
        material = (
            bool(new_facts)
            or candidate.status != old.status
            or abs(candidate.importance - old.importance) >= 2
        )
        if material:
            result.status = EventStatus.UPDATED if candidate.status == EventStatus.NEW else candidate.status
            result.updates.append(EventUpdate(
                at=candidate.updated_at,
                summary="Добавлены новые подтвержденные сведения или изменена оценка события.",
                article_ids=candidate.article_ids,
            ))
        else:
            result.updated_at = old.updated_at
        merged.append(result)

    # Keep earlier events that disappeared from one partial intraday run.
    merged.extend(previous.values())
    return sorted(merged, key=lambda event: (-event.importance, event.first_seen_at))

