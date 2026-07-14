from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, TypeVar

from pydantic import BaseModel

from trends.domain.models import Article, DigestEvent

from .base import AIProvider
from .schemas import ArticlePartition, EventRelationBatch, FeedAudit


T = TypeVar("T", bound=BaseModel)


class InvalidDedupeResponse(ValueError):
    pass


class DedupeService:
    def __init__(self, provider: AIProvider, prompts_root: Path | None = None) -> None:
        self.provider = provider
        self.prompts_root = prompts_root or Path(__file__).parent / "prompts"

    async def partition_articles(self, articles: list[Article]) -> ArticlePartition:
        payload = [
            {
                "article_id": article.id,
                "source_id": article.source_id,
                "language": article.language,
                "title": article.title,
                "excerpt": article.excerpt,
                "published_at": (
                    article.published_at or article.collected_at
                ).isoformat(),
            }
            for article in articles
        ]
        prompt = self._prompt("dedupe_partition_v1.md", payload)
        known = {article.id for article in articles}

        def validate(result: ArticlePartition) -> list[str]:
            flattened = [item for group in result.groups for item in group.article_ids]
            errors = []
            if set(flattened) != known:
                errors.append(
                    "groups must contain every input article_id and no unknown IDs"
                )
            if len(flattened) != len(set(flattened)):
                errors.append("each article_id must occur in exactly one group")
            group_by_article = {
                article_id: group_index
                for group_index, group in enumerate(result.groups)
                for article_id in group.article_ids
            }
            for relation in result.relations:
                if {relation.left_article_id, relation.right_article_id} - known:
                    errors.append("relations contain unknown article IDs")
                    continue
                if relation.left_article_id == relation.right_article_id:
                    errors.append("a relation cannot reference the same article twice")
                    continue
                same_group = (
                    group_by_article.get(relation.left_article_id)
                    == group_by_article.get(relation.right_article_id)
                )
                # Group assignment is the primary answer. Relations are
                # explanatory/advisory and Gemini can occasionally contradict
                # its otherwise complete partition. Rejecting the full answer
                # here loses a valid grouping and creates duplicate cards.
                _ = same_group
            return errors

        return await self._generate_with_repair(prompt, ArticlePartition, validate)

    async def classify_event_pairs(
        self,
        pairs: list[tuple[DigestEvent, DigestEvent, float]],
    ) -> EventRelationBatch:
        payload = [
            {
                "left": self._event_payload(left),
                "right": self._event_payload(right),
                "semantic_similarity": round(score, 4),
            }
            for left, right, score in pairs
        ]
        prompt = self._prompt("event_match_v1.md", payload)
        expected = {(left.id, right.id) for left, right, _ in pairs}

        def validate(result: EventRelationBatch) -> list[str]:
            actual = {
                (item.left_event_id, item.right_event_id)
                for item in result.decisions
            }
            errors = []
            if actual != expected:
                errors.append(
                    "return exactly one decision for every supplied left/right pair"
                )
            if len(actual) != len(result.decisions):
                errors.append("event pair decisions must be unique")
            return errors

        return await self._generate_with_repair(prompt, EventRelationBatch, validate)

    async def audit_feed(self, events: list[DigestEvent]) -> FeedAudit:
        aliases = {
            event.id: f"E{index:03d}"
            for index, event in enumerate(events, start=1)
        }
        aliases_to_ids = {alias: event_id for event_id, alias in aliases.items()}
        prompt = self._prompt(
            "feed_audit_v1.md",
            [
                {
                    **self._event_payload(event),
                    "event_id": aliases[event.id],
                }
                for event in events
            ],
        )
        # Real IDs remain accepted for deterministic test providers and older
        # compatible providers, while production prompts use short aliases that
        # Gemini copies much more reliably than hash-based IDs.
        known = {**aliases_to_ids, **{event.id: event.id for event in events}}

        def validate(result: FeedAudit) -> list[str]:
            used: set[str] = set()
            errors = []
            for group in result.duplicate_groups:
                ids = set(group.event_ids)
                if len(ids) != len(group.event_ids):
                    errors.append("duplicate group contains a repeated event ID")
                if ids - known.keys():
                    errors.append("duplicate group contains an unknown event ID")
                if ids & used:
                    errors.append("one event cannot occur in multiple duplicate groups")
                used.update(ids)
            return errors

        result = await self._generate_with_repair(prompt, FeedAudit, validate)
        return result.model_copy(
            update={
                "duplicate_groups": [
                    group.model_copy(
                        update={
                            "event_ids": [known[event_id] for event_id in group.event_ids]
                        }
                    )
                    for group in result.duplicate_groups
                ]
            }
        )

    async def _generate_with_repair(
        self,
        prompt: str,
        schema: type[T],
        validate: Callable[[T], list[str]],
    ) -> T:
        result = await self.provider.generate(prompt, schema)
        errors = validate(result)
        if not errors:
            return result
        repair = (
            f"{prompt}\n\nVALIDATION ERRORS:\n- "
            + "\n- ".join(errors)
            + "\nИсправь только эти ошибки и верни полный объект по той же JSON Schema."
        )
        result = await self.provider.generate(repair, schema)
        errors = validate(result)
        if errors:
            raise InvalidDedupeResponse("; ".join(errors))
        return result

    def _prompt(self, name: str, payload: object) -> str:
        policy = (self.prompts_root / name).read_text(encoding="utf-8")
        return f"{policy}\n\nINPUT:\n{json.dumps(payload, ensure_ascii=False)}"

    @staticmethod
    def _event_payload(event: DigestEvent) -> dict[str, object]:
        return {
            "event_id": event.id,
            "title": event.title,
            "brief": event.brief,
            "identity": (
                event.identity.model_dump(mode="json") if event.identity else None
            ),
            "article_ids": event.article_ids,
            "facts": [fact.text for fact in event.facts[:5]],
            "first_seen_at": event.first_seen_at.isoformat(),
            "updated_at": event.updated_at.isoformat(),
        }
