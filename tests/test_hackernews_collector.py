import asyncio
from datetime import UTC, datetime, timedelta

import httpx

from trends.collectors.base import CollectContext
from trends.collectors.hackernews import HackerNewsCollector
from trends.collectors.registry import default_registry
from trends.domain.enums import SourceState
from trends.domain.models import SourceConfig

NOW = datetime(2026, 7, 17, 12, tzinfo=UTC)


def source_config() -> SourceConfig:
    return SourceConfig(
        id="hackernews-backend",
        title="Hacker News Backend",
        type="hackernews",
        url="https://hacker-news.firebaseio.com/v0",
        tags=["tech", "python", "backend"],
        options={
            "scan_limit": 10,
            "limit": 5,
            "min_score": 80,
            "min_comments": 15,
            "max_age_hours": 36,
            "keywords": ["python", "postgres"],
        },
    )


def test_hackernews_filters_score_age_comments_and_topic() -> None:
    items = {
        1: {
            "id": 1,
            "type": "story",
            "title": "Python gets a faster free-threaded runtime",
            "url": "https://example.com/python-runtime",
            "score": 140,
            "descendants": 31,
            "time": int((NOW - timedelta(hours=2)).timestamp()),
        },
        2: {
            "id": 2,
            "type": "story",
            "title": "Postgres query planner internals",
            "url": "https://example.com/postgres",
            "score": 79,
            "descendants": 40,
            "time": int((NOW - timedelta(hours=2)).timestamp()),
        },
        3: {
            "id": 3,
            "type": "story",
            "title": "Python database pooling patterns",
            "url": "https://example.com/pooling",
            "score": 100,
            "descendants": 14,
            "time": int((NOW - timedelta(hours=2)).timestamp()),
        },
        4: {
            "id": 4,
            "type": "story",
            "title": "Postgres indexes at scale",
            "url": "https://example.com/indexes",
            "score": 120,
            "descendants": 25,
            "time": int((NOW - timedelta(hours=40)).timestamp()),
        },
        5: {
            "id": 5,
            "type": "story",
            "title": "Capital allocation in a browser engine",
            "url": "https://example.com/browser",
            "score": 180,
            "descendants": 50,
            "time": int((NOW - timedelta(hours=1)).timestamp()),
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/topstories.json"):
            return httpx.Response(200, json=list(items), request=request)
        story_id = int(request.url.path.split("/")[-1].removesuffix(".json"))
        return httpx.Response(200, json=items[story_id], request=request)

    async def collect():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await HackerNewsCollector(client).collect(
                CollectContext(started_at=NOW),
                source_config(),
            )

    result = asyncio.run(collect())

    assert result.state == SourceState.AVAILABLE
    assert [article.title for article in result.articles] == [
        "Python gets a faster free-threaded runtime"
    ]
    assert result.articles[0].engagement == 171
    assert result.articles[0].metadata["discussion_url"].endswith("id=1")


def test_hackernews_topstories_failure_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    async def collect():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await HackerNewsCollector(client).collect(
                CollectContext(started_at=NOW),
                source_config(),
            )

    result = asyncio.run(collect())

    assert result.state == SourceState.UNAVAILABLE
    assert result.articles == []
    assert result.error_code == "HTTPStatusError"


def test_hackernews_collector_is_registered() -> None:
    client = httpx.AsyncClient()
    collector = default_registry.create(source_config(), client)
    asyncio.run(client.aclose())

    assert isinstance(collector, HackerNewsCollector)
