from __future__ import annotations

from trends.domain.models import DailyDigest
from trends.pipeline.merge import assert_unique_article_ownership


def validate_digest_integrity(digest: DailyDigest) -> None:
    article_ids = [article.id for article in digest.articles]
    if len(article_ids) != len(set(article_ids)):
        raise ValueError("digest contains duplicate article IDs")
    event_ids = [event.id for event in digest.events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("digest contains duplicate event IDs")

    known_articles = set(article_ids)
    for event in digest.events:
        if len(event.article_ids) != len(set(event.article_ids)):
            raise ValueError(f"event {event.id} contains duplicate article IDs")
        event_articles = set(event.article_ids)
        unknown = event_articles - known_articles
        if unknown:
            raise ValueError(
                f"event {event.id} references unknown articles: {sorted(unknown)}"
            )
        for fact in event.facts:
            outside = set(fact.article_ids) - event_articles
            if outside:
                raise ValueError(
                    f"event {event.id} fact references articles outside the event: "
                    f"{sorted(outside)}"
                )
        for update in event.updates:
            outside = set(update.article_ids) - event_articles
            if outside:
                raise ValueError(
                    f"event {event.id} update references articles outside the event: "
                    f"{sorted(outside)}"
                )
    assert_unique_article_ownership(digest.events)
