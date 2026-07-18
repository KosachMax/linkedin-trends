import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from trends.ai.schemas import AIFact, EventSynthesis
from trends.ai.service import EventSynthesisService
from trends.ai.validate import validate_synthesis
from trends.config import load_digests, load_sources
from trends.domain.models import RawArticle
from trends.domain.enums import EventStatus, SourceState
from trends.domain.models import SourceRun
from trends.pipeline.dedupe import exact_dedupe
from trends.pipeline.fixture_builder import build_fixture_digests
from trends.pipeline.event_builder import build_event
from trends.pipeline.cluster import cluster_articles
from trends.pipeline.merge import merge_events
from trends.pipeline.normalize import normalize_articles
from trends.pipeline.select import select_for_digest
from trends.pipeline.production import _verification_status


ROOT = Path(__file__).parents[1]


def fixture_articles():
    payload = json.loads((ROOT / "tests/fixtures/articles.json").read_text(encoding="utf-8"))
    collected_at = datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00"))
    return normalize_articles(
        [RawArticle(**item, collected_at=collected_at) for item in payload["articles"]]
    )


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
    articles = normalize_articles(
        [
            RawArticle(**base, url="https://Example.com/story/?utm_source=test#top"),
            RawArticle(**base, url="https://example.com/story"),
        ]
    )
    assert len(exact_dedupe(articles)) == 1


def test_url_normalization_supports_source_specific_tracking_parameters():
    now = datetime.now(UTC)
    base = dict(source_id="demo", source_name="Demo", title="Same article", collected_at=now)
    articles = normalize_articles(
        [
            RawArticle(
                **base,
                url="https://example.com/story?campaign=daily",
                metadata={"ignored_query_params": ["campaign"]},
            ),
            RawArticle(**base, url="https://example.com/story"),
        ]
    )
    assert len(exact_dedupe(articles)) == 1


def test_url_normalization_sorts_query_parameters():
    now = datetime.now(UTC)
    base = dict(source_id="demo", source_name="Demo", title="Same article", collected_at=now)
    articles = normalize_articles(
        [
            RawArticle(**base, url="https://example.com/story?a=1&b=2"),
            RawArticle(**base, url="https://example.com/story?b=2&a=1"),
        ]
    )
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


def test_ai_validation_rejects_mostly_english_editorial_text():
    article = fixture_articles()[0]
    mixed = "Я " + "This entire editorial paragraph remains in English. " * 6
    synthesis = EventSynthesis(
        title="Я English headline",
        brief=mixed,
        context=mixed,
        why_it_matters=mixed,
        category="Я tech",
        impact=8,
        status="new",
        article_ids=[article.id],
        facts=[AIFact(text=mixed, article_ids=[article.id])],
    )
    errors = validate_synthesis(synthesis, [article], minimum_sources=1)
    assert any("predominantly" in error for error in errors)


def test_ai_validation_requires_complete_unique_event_provenance():
    first, second = fixture_articles()[:2]
    synthesis = EventSynthesis(
        title="Проверенное событие",
        brief="Подробная проверенная сводка события на русском языке. " * 6,
        context="Расширенный контекст события на русском языке. " * 7,
        why_it_matters="Объяснение важности события и его последствий. " * 4,
        category="мир",
        impact=7,
        status="new",
        article_ids=[first.id, first.id],
        facts=[AIFact(text="Подтвержденный факт", article_ids=[second.id])],
    )

    errors = validate_synthesis(synthesis, [first, second], minimum_sources=1)

    assert "event article_ids must not contain duplicates" in errors
    assert any("every input article id" in error for error in errors)
    assert any("outside the event" in error for error in errors)


def test_fixture_builder_writes_current_and_archive(tmp_path):
    # The builder receives a project-shaped root, so reuse immutable configs/fixtures.
    (tmp_path / "tests").symlink_to(ROOT / "tests", target_is_directory=True)
    (tmp_path / "config").symlink_to(ROOT / "config", target_is_directory=True)
    paths = build_fixture_digests(tmp_path)
    assert len(paths) == 4
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


def test_digest_source_tags_exclude_unrelated_publishers():
    world = next(
        profile for profile in load_digests(ROOT / "config/digests") if profile.id == "world"
    )
    raw = RawArticle(
        source_id="technical-only",
        source_name="Technical Only",
        url="https://example.com/world-report",
        title="World leaders meet",
        collected_at=datetime.now(UTC),
        topic_hints=["tech"],
    )
    assert select_for_digest(normalize_articles([raw]), world) == []


def test_ai_prompt_discloses_source_origin_and_ownership():
    import asyncio

    article = normalize_articles(
        [
            RawArticle(
                source_id="state-wire",
                source_name="State Wire",
                url="https://example.com/claim",
                title="Military issues a battlefield claim",
                collected_at=datetime.now(UTC),
                source_perspective="russian",
                source_ownership="state",
                source_disclosure="Treat battlefield reports as claims.",
            )
        ]
    )[0]
    prompt = asyncio.run(EventSynthesisService(object())._prompt([article]))
    assert '"source_name": "State Wire"' in prompt
    assert '"source_perspective": "russian"' in prompt
    assert '"source_ownership": "state"' in prompt
    assert '"source_trust_tier": "major"' in prompt
    assert "Treat battlefield reports as claims." in prompt


def test_frontline_verification_is_computed_from_source_provenance():
    import asyncio

    profile = next(
        profile for profile in load_digests(ROOT / "config/digests") if profile.id == "ukraine-war"
    )
    now = datetime.now(UTC)
    articles = normalize_articles(
        [
            RawArticle(
                source_id="ru-state",
                source_name="Russian State",
                url="https://example.com/ru-state",
                title="Военное ведомство сообщило об изменении на фронте",
                collected_at=now,
                source_perspective="russian",
                source_ownership="state",
            ),
            RawArticle(
                source_id="ru-independent",
                source_name="Russian Independent",
                url="https://example.com/ru-independent",
                title="Русскоязычное издание описало изменение на фронте",
                collected_at=now,
                source_perspective="russian",
                source_ownership="independent",
            ),
            RawArticle(
                source_id="ua-independent",
                source_name="Ukrainian Independent",
                url="https://example.com/ua-independent",
                title="Украинское издание сообщило об изменении на фронте",
                collected_at=now,
                source_perspective="ukrainian",
                source_ownership="independent",
            ),
            RawArticle(
                source_id="international-public",
                source_name="International Public",
                url="https://example.com/international-public",
                title="Международное издание независимо проверило сообщение",
                collected_at=now,
                source_perspective="international",
                source_ownership="public",
            ),
        ]
    )
    event = asyncio.run(build_event(profile, [articles[0]], now, None))

    assert _verification_status(profile, event, [articles[0]]) == "single_source"
    assert _verification_status(profile, event, articles[:2]) == "same_perspective"
    assert _verification_status(profile, event, articles[:3]) == "cross_perspective"
    assert _verification_status(profile, event, articles) == "independent_confirmation"
    disputed = event.model_copy(update={"status": EventStatus.DISPUTED})
    assert _verification_status(profile, disputed, articles) == "conflicting_accounts"


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


def test_intraday_merge_only_marks_material_changes(tmp_path):
    (tmp_path / "tests").symlink_to(ROOT / "tests", target_is_directory=True)
    (tmp_path / "config").symlink_to(ROOT / "config", target_is_directory=True)
    build_fixture_digests(tmp_path)
    digest = json.loads((tmp_path / "data/digests/world/current.json").read_text(encoding="utf-8"))
    from trends.domain.models import DailyDigest, Fact

    parsed = DailyDigest.model_validate(digest)
    old = parsed.events[0]
    source_only = deepcopy(old)
    source_only.article_ids.append(parsed.articles[-1].id)
    unchanged = merge_events([old], [source_only])[0]
    assert unchanged.status == old.status
    assert unchanged.updates == []
    assert unchanged.title == old.title

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
    assert {path.parents[3].name for path in written} == {
        "world",
        "tech",
        "fc-liverpool",
        "ukraine-war",
    }
    world = json.loads((tmp_path / "data/digests/world/current.json").read_text(encoding="utf-8"))
    assert world["schema_version"] == 2
    assert world["events"]
    known_article_ids = {article["id"] for article in world["articles"]}
    published_article_ids = [
        article_id for event in world["events"] for article_id in event["article_ids"]
    ]
    assert set(published_article_ids) <= known_article_ids
    assert len(published_article_ids) == len(set(published_article_ids))
    reports = list((tmp_path / "data/runs").glob("*/*/*/*.json"))
    assert reports
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert "exact_url_duplicates" in report["dedupe"]
    world_metrics = report["digests"]["world"]["dedupe"]
    assert world_metrics["thresholds"]["lookback_hours"] == 72
    assert world_metrics["dedupe_degraded"] is True


def test_production_synthesizes_only_twice_the_visible_event_limit(tmp_path, monkeypatch):
    import asyncio
    from trends.pipeline import production

    (tmp_path / "config").symlink_to(ROOT / "config", target_is_directory=True)
    collected_at = datetime(2026, 7, 14, 12, tzinfo=UTC)
    raw = [
        RawArticle(
            id=f"tech-{index}",
            source_id=f"source-{index}",
            source_name=f"Source {index}",
            url=f"https://example.com/tech/{index}",
            title=f"Tech release number {index}",
            excerpt=f"A distinct technology report numbered {index}.",
            collected_at=collected_at,
            published_at=collected_at,
            topic_hints=["tech"],
        )
        for index in range(25)
    ]
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

    async def singleton_partition(selected, _profile, _provider, _dedupe_ai, _metrics):
        return [[article] for article in selected]

    real_build_event = production.build_event
    synthesis_calls = 0

    async def counted_build_event(profile, cluster, started, _ai, **kwargs):
        nonlocal synthesis_calls
        synthesis_calls += 1
        return await real_build_event(profile, cluster, started, None, **kwargs)

    monkeypatch.setattr(production, "collect_sources", fake_collect_sources)
    monkeypatch.setattr(production, "partition_articles", singleton_partition)
    monkeypatch.setattr(production, "build_event", counted_build_event)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    asyncio.run(production.run_production(tmp_path))

    report_path = next((tmp_path / "data/runs").glob("*/*/*/*.json"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    metrics = report["digests"]["tech"]["dedupe"]
    assert synthesis_calls == 20
    assert metrics["candidate_clusters"] == 25
    assert metrics["synthesized_clusters"] == 20
    assert metrics["skipped_low_rank_clusters"] == 5
