from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from trends.ai.dedupe_service import DedupeService
from trends.ai.gemini import GeminiProvider
from trends.ai.schemas import (
    AIEventIdentity,
    ArticlePartition,
    ArticlePartitionGroup,
    ArticleRelationDecision,
    EventRelationBatch,
    EventRelationDecision,
    FeedAuditGroup,
    EventSynthesis,
)
from trends.config import load_digests
from trends.domain.enums import EventStatus
from trends.domain.models import (
    DailyDigest,
    DailyPicture,
    DedupeConfig,
    DigestEvent,
    Fact,
    RawArticle,
    SourceRun,
)
from trends.pipeline.dedupe import dedupe_articles
from trends.pipeline.event_builder import partition_articles, stable_event_id
from trends.pipeline.event_lifecycle import audit_feed, merge_with_recent
from trends.pipeline.merge import collapse_article_overlaps
from trends.pipeline.normalize import normalize_articles
from trends.pipeline.semantic import build_candidate_bundles, similarity_matrix
from trends.storage.archive_repair import repair_archive
from trends.storage.daily_store import DailyStore


ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 7, 12, 12, tzinfo=UTC)


def make_article(
    article_id: str,
    source_id: str,
    title: str,
    excerpt: str,
    *,
    age_hours: int = 0,
    url_suffix: str | None = None,
):
    return normalize_articles([
        RawArticle(
            id=article_id,
            source_id=source_id,
            source_name=source_id,
            url=f"https://example.com/{url_suffix or article_id}",
            title=title,
            excerpt=excerpt,
            published_at=NOW - timedelta(hours=age_hours),
            collected_at=NOW,
        )
    ])[0]


def make_event(
    event_id: str,
    title: str,
    updated_at: datetime,
    article_id: str,
) -> DigestEvent:
    return DigestEvent(
        id=event_id,
        slug=event_id,
        title=title,
        brief="Подробная проверенная сводка события на русском языке. " * 5,
        context="Расширенный контекст события на русском языке. " * 5,
        why_it_matters="Объяснение важности события и его последствий. " * 4,
        importance=8,
        status=EventStatus.NEW,
        category="спорт",
        article_ids=[article_id],
        facts=[
            Fact(
                text=f"Подтвержден новый факт для {title}",
                article_ids=[article_id],
            )
        ],
        first_seen_at=updated_at,
        updated_at=updated_at,
    )


def world_profile():
    return {
        item.id: item for item in load_digests(ROOT / "config/digests")
    }["world"]


def test_gemini_response_schemas_do_not_emit_unsupported_additional_properties():
    schemas = [
        AIEventIdentity,
        EventSynthesis,
        ArticlePartition,
        EventRelationBatch,
    ]
    for schema in schemas:
        serialized = json.dumps(schema.model_json_schema())
        assert "additionalProperties" not in serialized


def test_same_source_near_copies_collapse_but_cross_source_copy_remains():
    first = make_article(
        "a", "source-a", "Same headline", "Exactly the same article body"
    )
    same_source = make_article(
        "b",
        "source-a",
        "Same headline",
        "Exactly the same article body",
    )
    cross_source = make_article(
        "c",
        "source-b",
        "Same headline",
        "Exactly the same article body",
    )

    result, stats = dedupe_articles([first, same_source, cross_source])

    assert [article.id for article in result] == ["a", "c"]
    assert stats.same_source_near_duplicates == 1


def test_same_url_from_different_sources_remains_as_independent_evidence():
    first = make_article(
        "a",
        "source-a",
        "Shared canonical report",
        "The first source linked the report.",
        url_suffix="shared",
    )
    second = make_article(
        "b",
        "source-b",
        "Shared canonical report",
        "The second source independently linked the report.",
        url_suffix="shared",
    )

    result, stats = dedupe_articles([first, second])

    assert [article.id for article in result] == ["a", "b"]
    assert stats.exact_url_duplicates == 0


def test_multilingual_world_cup_regression_keeps_related_news_separate():
    payload = json.loads(
        (ROOT / "tests/fixtures/dedupe_world_cup.json").read_text(
            encoding="utf-8"
        )
    )
    articles = [
        make_article(
            item["id"], item["source_id"], item["title"], item["excerpt"]
        )
        for item in payload["articles"]
    ]
    vectors = [
        [1.0, 0.02, 0.0],
        [0.99, 0.03, 0.0],
        [0.98, 0.04, 0.0],
        [0.97, 0.05, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 0.7, 0.7],
    ]

    bundles, _ = build_candidate_bundles(
        articles,
        similarity_matrix(vectors),
        DedupeConfig(),
    )

    actual = sorted(sorted(article.id for article in bundle) for bundle in bundles)
    expected = sorted(sorted(group) for group in payload["expected_groups"])
    assert actual == expected


def test_stable_event_id_does_not_depend_on_generated_title():
    articles = [
        make_article("first", "one", "Original headline", "Original report"),
        make_article("second", "two", "Different wording", "Same report"),
    ]

    assert stable_event_id("world", articles) == stable_event_id(
        "world", list(reversed(articles))
    )


class SplittingProvider:
    embedding_model = "test-multilingual-embedding"

    async def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]

    async def generate(self, _prompt, schema):
        return schema(
            groups=[
                ArticlePartitionGroup(article_ids=["match-result"]),
                ArticlePartitionGroup(article_ids=["partnership"]),
            ],
            relations=[
                ArticleRelationDecision(
                    left_article_id="match-result",
                    right_article_id="partnership",
                    relation="different",
                    confidence=0.99,
                )
            ],
        )


def test_ai_partition_keeps_same_participants_but_different_actions_separate():
    articles = [
        make_article(
            "match-result",
            "sport-one",
            "England beat Norway 2-1",
            "England won the World Cup quarter-final after extra time.",
        ),
        make_article(
            "partnership",
            "sport-two",
            "England and Norway launch youth football partnership",
            "The federations signed a three-year coaching agreement.",
        ),
    ]
    provider = SplittingProvider()
    metrics = {}

    result = asyncio.run(
        partition_articles(
            articles,
            world_profile(),
            provider,
            DedupeService(provider),
            metrics,
        )
    )

    assert [[article.id for article in cluster] for cluster in result] == [
        ["match-result"],
        ["partnership"],
    ]
    assert metrics["ai_splits"] == 1


def test_candidate_window_does_not_join_same_text_after_73_hours():
    articles = [
        make_article(
            "new", "one", "Repeated headline", "Repeated event", age_hours=0
        ),
        make_article(
            "old", "two", "Repeated headline", "Repeated event", age_hours=73
        ),
    ]
    bundles, _ = build_candidate_bundles(
        articles,
        similarity_matrix([[1.0, 0.0], [1.0, 0.0]]),
        DedupeConfig(lookback_hours=72),
    )
    assert sorted(len(bundle) for bundle in bundles) == [1, 1]


class RepairingPartitionProvider:
    def __init__(self, article_ids: list[str]):
        self.article_ids = article_ids
        self.calls = 0

    async def generate(self, _prompt, schema):
        self.calls += 1
        ids = self.article_ids[:-1] if self.calls == 1 else self.article_ids
        return schema(
            groups=[ArticlePartitionGroup(article_ids=ids)],
            relations=[],
        )


def test_partition_response_is_repaired_when_an_article_is_missing():
    articles = [
        make_article("one", "a", "One", "First article"),
        make_article("two", "b", "Two", "Second article"),
    ]
    provider = RepairingPartitionProvider([article.id for article in articles])
    result = asyncio.run(DedupeService(provider).partition_articles(articles))
    assert isinstance(result, ArticlePartition)
    assert result.groups[0].article_ids == ["one", "two"]
    assert provider.calls == 2


class RepairingRelationProvider:
    def __init__(self):
        self.calls = 0

    async def generate(self, _prompt, schema):
        self.calls += 1
        groups = [
            ArticlePartitionGroup(article_ids=["one"]),
            ArticlePartitionGroup(article_ids=["two"]),
        ]
        relation = "same_event" if self.calls == 1 else "different"
        return schema(
            groups=groups,
            relations=[
                ArticleRelationDecision(
                    left_article_id="one",
                    right_article_id="two",
                    relation=relation,
                    confidence=0.99,
                )
            ],
        )


def test_partition_repairs_relation_that_contradicts_its_groups():
    articles = [
        make_article("one", "a", "One", "First article"),
        make_article("two", "b", "Two", "Second article"),
    ]
    provider = RepairingRelationProvider()

    result = asyncio.run(DedupeService(provider).partition_articles(articles))

    assert result.relations[0].relation == "different"
    assert provider.calls == 2


class AlwaysIncompleteProvider:
    embedding_model = "test-embedding"

    async def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]

    async def generate(self, _prompt, schema):
        return schema(
            groups=[ArticlePartitionGroup(article_ids=["one"])],
            relations=[],
        )


def test_invalid_ai_partition_degrades_without_losing_articles():
    articles = [
        make_article("one", "a", "Same event report", "First article"),
        make_article("two", "b", "Same event update", "Second article"),
    ]
    provider = AlwaysIncompleteProvider()
    metrics = {}

    result = asyncio.run(
        partition_articles(
            articles,
            world_profile(),
            provider,
            DedupeService(provider),
            metrics,
        )
    )

    assert sorted(
        article.id for cluster in result for article in cluster
    ) == ["one", "two"]
    assert metrics["degraded"] is True
    assert any(
        error.startswith("partition:InvalidDedupeResponse")
        for error in metrics["errors"]
    )


class WrongSizedEmbeddingProvider:
    embedding_model = "broken-embedding"

    async def embed(self, _texts):
        return [[1.0, 0.0]]

    async def generate(self, _prompt, _schema):
        raise AssertionError("unrelated lexical singletons need no AI partition")


def test_wrong_embedding_count_degrades_without_aborting_the_digest():
    articles = [
        make_article("one", "a", "Energy agreement", "New energy reserve"),
        make_article("two", "b", "Python release", "New runtime release"),
    ]
    provider = WrongSizedEmbeddingProvider()
    metrics = {}

    result = asyncio.run(
        partition_articles(
            articles,
            world_profile(),
            provider,
            DedupeService(provider),
            metrics,
        )
    )

    assert sorted(
        article.id for cluster in result for article in cluster
    ) == ["one", "two"]
    assert metrics["degraded"] is True
    assert any(error.startswith("embeddings:ValueError") for error in metrics["errors"])


def test_gemini_embedding_provider_returns_one_vector_per_text():
    captured = {}

    class Models:
        async def embed_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                embeddings=[
                    SimpleNamespace(values=[1.0, 0.0]),
                    SimpleNamespace(values=[0.0, 1.0]),
                ]
            )

    provider = GeminiProvider("test-key")
    provider.client = SimpleNamespace(aio=SimpleNamespace(models=Models()))
    result = asyncio.run(provider.embed(["first", "second"]))

    assert result == [[1.0, 0.0], [0.0, 1.0]]
    assert captured["model"] == "gemini-embedding-2"
    assert len(captured["contents"]) == 2


class MatchingProvider:
    def __init__(self, left_id: str, right_id: str):
        self.left_id = left_id
        self.right_id = right_id

    async def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]

    async def generate(self, _prompt, schema):
        return EventRelationBatch(
            decisions=[
                EventRelationDecision(
                    left_event_id=self.left_id,
                    right_event_id=self.right_id,
                    relation="update_of",
                    confidence=0.99,
                )
            ]
        )


def test_update_within_24_hours_reuses_event_id_and_writes_history():
    old = make_event("old-id", "Англия победила Норвегию", NOW, "old-article")
    candidate = make_event(
        "new-id",
        "Опубликованы подробности победы Англии",
        NOW + timedelta(hours=24),
        "new-article",
    )
    provider = MatchingProvider(candidate.id, old.id)
    metrics = {}

    result = asyncio.run(
        merge_with_recent(
            [candidate],
            [old],
            None,
            world_profile(),
            provider,
            DedupeService(provider),
            metrics,
        )
    )

    assert result[0].id == old.id
    assert result[0].article_ids == ["old-article", "new-article"]
    assert result[0].updates
    assert "Подтвержден новый факт" in result[0].updates[-1].summary


def test_update_after_73_hours_keeps_a_new_event_id():
    old = make_event("old-id", "Повторяющееся событие", NOW, "old-article")
    candidate = make_event(
        "new-id",
        "Повторяющееся событие",
        NOW + timedelta(hours=73),
        "new-article",
    )
    provider = MatchingProvider(candidate.id, old.id)

    result = asyncio.run(
        merge_with_recent(
            [candidate],
            [old],
            None,
            world_profile(),
            provider,
            DedupeService(provider),
            {},
        )
    )

    assert [event.id for event in result] == [candidate.id]


def test_cards_sharing_an_article_are_collapsed_before_publication():
    events = [
        make_event("one", "Первая формулировка", NOW, "shared-article"),
        make_event("two", "Вторая формулировка", NOW, "shared-article"),
        make_event("three", "Третья формулировка", NOW, "shared-article"),
        make_event("four", "Четвертая формулировка", NOW, "shared-article"),
    ]

    result, merged_count = collapse_article_overlaps(events)

    assert len(result) == 1
    assert merged_count == 3
    assert result[0].article_ids == ["shared-article"]


class AuditProvider:
    def __init__(self, event_ids: list[str]):
        self.event_ids = event_ids

    async def generate(self, _prompt, schema):
        return schema(
            duplicate_groups=[
                FeedAuditGroup(
                    event_ids=self.event_ids,
                    relation="same_event",
                    confidence=0.99,
                )
            ]
        )


def test_final_audit_merges_duplicate_cards_without_losing_provenance():
    events = [
        make_event("first", "Англия победила Норвегию", NOW, "article-one"),
        make_event(
            "second", "Итоги матча Англия — Норвегия", NOW, "article-two"
        ),
    ]
    provider = AuditProvider([event.id for event in events])
    metrics = {}

    result = asyncio.run(
        audit_feed(
            events,
            {},
            world_profile(),
            NOW,
            None,
            DedupeService(provider),
            metrics,
        )
    )

    assert len(result) == 1
    assert result[0].id == "first"
    assert result[0].article_ids == ["article-one", "article-two"]
    assert metrics["final_audit_merges"] == 1


def test_final_audit_keeps_merged_card_when_resynthesis_fails():
    events = [
        make_event("first", "Англия победила Норвегию", NOW, "article-one"),
        make_event(
            "second", "Итоги матча Англия — Норвегия", NOW, "article-two"
        ),
    ]
    articles = {
        "article-one": make_article(
            "article-one", "one", "England won", "First report"
        ),
        "article-two": make_article(
            "article-two", "two", "England beat Norway", "Second report"
        ),
    }
    provider = AuditProvider([event.id for event in events])

    class FailingSynthesis:
        async def synthesize(self, _articles, minimum_sources):
            raise RuntimeError("generation unavailable")

    metrics = {}
    result = asyncio.run(
        audit_feed(
            events,
            articles,
            world_profile(),
            NOW,
            FailingSynthesis(),
            DedupeService(provider),
            metrics,
        )
    )

    assert len(result) == 1
    assert result[0].article_ids == ["article-one", "article-two"]
    assert metrics["degraded"] is True
    assert any(
        error.startswith("audit_resynthesis:RuntimeError")
        for error in metrics["errors"]
    )


def test_archive_repair_merges_confirmed_groups_and_updates_current(tmp_path):
    articles = [
        make_article("article-one", "one", "England won", "First report"),
        make_article(
            "article-two", "two", "England beat Norway", "Second report"
        ),
    ]
    events = [
        make_event("first", "Англия победила Норвегию", NOW, "article-one"),
        make_event(
            "second", "Итоги матча Англия — Норвегия", NOW, "article-two"
        ),
    ]
    digest = DailyDigest(
        digest_id="world",
        date=NOW.date(),
        generated_at=NOW,
        daily_picture=DailyPicture(body="Исходный тестовый выпуск."),
        sources=[
            SourceRun(
                source_id=article.source_id,
                source_name=article.source_name,
                state="available",
                fetched=1,
                accepted=1,
                represented_events=1,
            )
            for article in articles
        ],
        articles=articles,
        events=events,
    )
    DailyStore(tmp_path / "data/digests").write(digest)

    report = repair_archive(
        tmp_path,
        "world",
        NOW.date(),
        [["first", "second"]],
    )

    repaired = DailyDigest.model_validate_json(
        (tmp_path / "data/digests/world/current.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["events_before"] == 2
    assert report["events_after"] == 1
    assert repaired.schema_version == 2
    assert len(repaired.events) == 1
    assert repaired.events[0].article_ids == ["article-one", "article-two"]
    assert all(source.represented_events == 1 for source in repaired.sources)
