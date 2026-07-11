from datetime import UTC, datetime
from time import perf_counter

import feedparser
import httpx

from trends.domain.enums import SourceState
from trends.domain.models import RawArticle, SourceConfig

from .base import CollectContext, CollectorResult


class RssCollector:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def collect(self, context: CollectContext, config: SourceConfig) -> CollectorResult:
        started = perf_counter()
        try:
            response = await self.client.get(str(config.url), timeout=config.timeout_seconds)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            limit = int(config.options.get("limit", 20))
            articles = []
            for entry in feed.entries[:limit]:
                url = entry.get("link", "")
                title = entry.get("title", "").strip()
                if not url or not title:
                    continue
                published = entry.get("published_parsed")
                published_at = datetime(*published[:6], tzinfo=UTC) if published else None
                articles.append(RawArticle(
                    source_id=config.id,
                    source_name=config.title,
                    url=url,
                    title=title,
                    excerpt=(entry.get("summary") or entry.get("description") or "")[:1000],
                    published_at=published_at,
                    collected_at=context.started_at,
                    language=config.language,
                    topic_hints=config.tags,
                ))
            state = SourceState.AVAILABLE if articles else SourceState.DEGRADED
            return CollectorResult(articles=articles, state=state, latency_ms=int((perf_counter() - started) * 1000))
        except (httpx.HTTPError, ValueError) as error:
            return CollectorResult(
                state=SourceState.UNAVAILABLE,
                latency_ms=int((perf_counter() - started) * 1000),
                error_code=type(error).__name__,
            )
