import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from trends.ai.schemas import AIFact, EventSynthesis
from trends.ai.service import EventSynthesisService
from trends.ai.validate import validate_synthesis
from trends.config import load_digests, load_sources
from trends.domain.models import RawArticle
from trends.domain.enums import SourceState
from trends.domain.models import SourceRun
from trends.pipeline.dedupe import exact_dedupe
from trends.pipeline.fixture_builder import build_fixture_digests
from trends.pipeline.cluster import cluster_articles
from trends.pipeline.merge import merge_events
from trends.pipeline.normalize import normalize_articles
from trends.pipeline.select import select_for_digest


ROOT = Path(__file__).parents[1]


def fixture_articles():
    payload = json.loads((ROOT / "tests/fixtures/articles.json").read_text(encoding="utf-8"))
    collected_at = datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00"))
    return normalize_articles([RawArticle(**item, collected_at=collected_at) for item in payload["articles"]])


def test_digest_profiles_match_expected_fixture_membership():
    payload = json.loads((ROOT / "tests/fixtures/articles.json").read_text(encoding="utf-8"))
    articles = fixture_articles()
    profiles = {profile.id: profile for profile in load_digests(ROOT / "config/digests")}
    for digest_id, expected in payload["expected_digest_membership"].items():
        selected = select_for_digest(articles, profiles[digest_id])
        assert {article.id for article in selected} == set(expected)


def test_url_normalization_removes_tracking_and_exact_duplicates():
    now = datetime.now(UTC)
    base = dict(source_id="demo", source_name="Demo", title="Same article", collected_at=now)
    articles = normalize_articles([
        RawArticle(**base, url="https://Example.com/story/?utm_source=test#top"),
        RawArticle(**base, url="https://example.com/story"),
    ])
    assert len(exact_dedupe(articles)) == 1


def test_ai_validation_rejects_unknown_article_reference():
    article = fixture_articles()[0]
    synthesis = EventSynthesis(
        title="Test event",
        brief="B" * 220,
        context="C" * 220,
        why_it_matters="W" * 170,
        category="world",
        impact=8,
        status="new",
        article_ids=[article.id, "invented-id"],
        facts=[AIFact(text="Claim", article_ids=["invented-id"])],
    )
    errors = validate_synthesis(synthesis, [article], minimum_sources=1)
    assert any("unknown article ids" in error for error in errors)
    assert any("fact 0" in error for error in errors)


def test_fixture_builder_writes_current_and_archive(tmp_path):
    # The builder receives a project-shaped root, so reuse immutable configs/fixtures.
    (tmp_path / "tests").symlink_to(ROOT / "tests", target_is_directory=True)
    (tmp_path / "config").symlink_to(ROOT / "config", target_is_directory=True)
    paths = build_fixture_digests(tmp_path)
    assert len(paths) == 3
    for path in paths:
        assert path.exists()
        digest_root = path.parents[3]
        assert (digest_root / "current.json").exists()
        assert (digest_root / "archive-index.json").exists()
        assert (digest_root / "source-history.json").exists()


def test_all_source_configs_are_valid():
    sources = load_sources(ROOT / "config/sources")
    assert len(sources) >= 4
    assert len({source.id for source in sources}) == len(sources)
    assert all(source.url for source in sources if source.type == "rss")


class RepairingProvider:
    def __init__(self, valid_article_id: str):
        self.valid_article_id = valid_article_id
        self.calls = 0

    async def generate(self, prompt, schema):
        self.calls += 1
        article_id = "invented-id" if self.calls == 1 else self.valid_article_id
        return schema(
            title="Структурированное событие",
            brief="Краткая проверенная сводка события на русском языке. " * 6,
            context="Расширенный контекст события на русском языке. " * 7,
            why_it_matters="Объяснение важности события и его возможных последствий. " * 4,
            category="мир",
            impact=7,
            status="new",
            article_ids=[article_id],
            facts=[AIFact(text="Подтвержденный источником факт", article_ids=[article_id])],
        )


def test_ai_service_repairs_once():
    import asyncio

    article = fixture_articles()[0]
    provider = RepairingProvider(article.id)
    result = asyncio.run(EventSynthesisService(provider).synthesize([article], minimum_sources=1))
    assert result.article_ids == [article.id]
    assert provider.calls == 2


def test_intraday_merge_only_marks_material_changes():
    tmp_root = ROOT
    build_fixture_digests(tmp_root)
    digest = json.loads((ROOT / "data/digests/world/current.json").read_text(encoding="utf-8"))
    from trends.domain.models import DailyDigest, Fact

    parsed = DailyDigest.model_validate(digest)
    old = parsed.events[0]
    source_only = deepcopy(old)
    source_only.article_ids.append(parsed.articles[-1].id)
    unchanged = merge_events([old], [source_only])[0]
    assert unchanged.status == old.status
    assert unchanged.updates == []

    material = deepcopy(old)
    material.facts.append(Fact(text="A newly confirmed fact", article_ids=[old.article_ids[0]]))
    updated = merge_events([old], [material])[0]
    assert updated.status.value == "updated"
    assert len(updated.updates) == 1


def test_similar_cross_source_titles_form_one_cluster():
    articles = fixture_articles()
    energy = [article for article in articles if "energy" in article.topic_hints]
    clusters = cluster_articles(energy)
    assert len(clusters) == 1
    assert {article.source_id for article in clusters[0]} == {"reuters", "bbc-world"}


def test_production_runner_builds_digests_without_ai(tmp_path, monkeypatch):
    import asyncio
    from trends.pipeline import production

    (tmp_path / "config").symlink_to(ROOT / "config", target_is_directory=True)
    payload = json.loads((ROOT / "tests/fixtures/articles.json").read_text(encoding="utf-8"))
    collected_at = datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00"))
    raw = [RawArticle(**item, collected_at=collected_at) for item in payload["articles"]]
    runs = [
        SourceRun(
            source_id=item.source_id,
            source_name=item.source_name,
            state=SourceState.AVAILABLE,
            fetched=1,
        )
        for item in raw
    ]

    async def fake_collect_sources(_configs):
        return raw, runs

    monkeypatch.setattr(production, "collect_sources", fake_collect_sources)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    written = asyncio.run(production.run_production(tmp_path))
    assert {path.parents[3].name for path in written} == {"world", "tech", "fc-liverpool"}
    world = json.loads((tmp_path / "data/digests/world/current.json").read_text(encoding="utf-8"))
    assert len(world["events"]) >= 1
    assert len(world["events"][0]["article_ids"]) >= 1
    assert list((tmp_path / "data/runs").glob("*/*/*/*.json"))
