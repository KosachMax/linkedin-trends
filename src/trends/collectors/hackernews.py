import asyncio
import re
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import httpx

from trends.domain.enums import SourceState
from trends.domain.models import RawArticle, SourceConfig

from .base import CollectContext, CollectorResult


DEFAULT_API_URL = "https://hacker-news.firebaseio.com/v0"


class HackerNewsCollector:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def collect(self, context: CollectContext, config: SourceConfig) -> CollectorResult:
        started = perf_counter()
        base_url = str(config.url or DEFAULT_API_URL).rstrip("/")
        scan_limit = int(config.options.get("scan_limit", 100))
        limit = int(config.options.get("limit", 20))
        min_score = int(config.options.get("min_score", 80))
        min_comments = int(config.options.get("min_comments", 15))
        max_age_hours = int(config.options.get("max_age_hours", 36))
        keywords = {
            str(value).casefold()
            for value in config.options.get("keywords", [])
            if str(value).strip()
        }

        try:
            response = await self.client.get(
                f"{base_url}/topstories.json",
                timeout=config.timeout_seconds,
            )
            response.raise_for_status()
            story_ids = response.json()
            if not isinstance(story_ids, list):
                raise ValueError("Hacker News topstories response must be a list")
        except (httpx.HTTPError, ValueError) as error:
            return CollectorResult(
                state=SourceState.UNAVAILABLE,
                latency_ms=int((perf_counter() - started) * 1000),
                error_code=type(error).__name__,
            )

        semaphore = asyncio.Semaphore(20)

        async def fetch_item(story_id: int) -> dict[str, Any]:
            async with semaphore:
                item_response = await self.client.get(
                    f"{base_url}/item/{story_id}.json",
                    timeout=config.timeout_seconds,
                )
                item_response.raise_for_status()
                payload = item_response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Hacker News item response must be an object")
                return payload

        results = await asyncio.gather(
            *(fetch_item(story_id) for story_id in story_ids[:scan_limit]),
            return_exceptions=True,
        )

        articles: list[RawArticle] = []
        for item in results:
            if isinstance(item, BaseException):
                continue
            if item.get("type") != "story" or item.get("dead") or item.get("deleted"):
                continue

            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            score = int(item.get("score") or 0)
            comments = int(item.get("descendants") or 0)
            published_timestamp = item.get("time")
            if not title or not url or score < min_score or comments < min_comments:
                continue
            if not isinstance(published_timestamp, (int, float)):
                continue

            published_at = datetime.fromtimestamp(published_timestamp, tz=UTC)
            age_hours = (context.started_at - published_at).total_seconds() / 3600
            if age_hours < 0 or age_hours > max_age_hours:
                continue

            searchable = f"{title} {item.get('text') or ''}".casefold()
            if keywords and not any(
                re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", searchable) for keyword in keywords
            ):
                continue

            articles.append(
                RawArticle(
                    source_id=config.id,
                    source_name=config.title,
                    url=url,
                    title=title,
                    excerpt=str(item.get("text") or "")[:1000] or None,
                    published_at=published_at,
                    collected_at=context.started_at,
                    language=config.language,
                    topic_hints=config.tags,
                    source_perspective=config.perspective,
                    source_ownership=config.ownership,
                    source_disclosure=config.editorial_note,
                    source_trust_tier=config.trust_tier,
                    engagement=score + comments,
                    metadata={
                        "hackernews_id": str(item.get("id") or ""),
                        "score": score,
                        "comments": comments,
                        "discussion_url": (
                            f"https://news.ycombinator.com/item?id={item.get('id')}"
                        ),
                    },
                )
            )
            if len(articles) >= limit:
                break

        return CollectorResult(
            articles=articles,
            state=SourceState.AVAILABLE if articles else SourceState.DEGRADED,
            latency_ms=int((perf_counter() - started) * 1000),
        )
