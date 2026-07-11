import asyncio
from datetime import UTC, datetime

import httpx

from trends.domain.models import RawArticle, SourceConfig, SourceRun

from .base import CollectContext
from .registry import CollectorRegistry, default_registry


async def collect_sources(
    configs: list[SourceConfig], registry: CollectorRegistry = default_registry
) -> tuple[list[RawArticle], list[SourceRun]]:
    context = CollectContext(started_at=datetime.now(UTC))
    enabled = [config for config in configs if config.enabled]
    async with httpx.AsyncClient(follow_redirects=True, headers={"User-Agent": "linkedin-trends/0.2"}) as client:
        async def run(config: SourceConfig):
            result = await registry.create(config, client).collect(context, config)
            return config, result

        results = await asyncio.gather(*(run(config) for config in enabled))

    articles: list[RawArticle] = []
    source_runs: list[SourceRun] = []
    for config, result in results:
        articles.extend(result.articles)
        source_runs.append(SourceRun(
            source_id=config.id,
            source_name=config.title,
            state=result.state,
            fetched=len(result.articles),
            latency_ms=result.latency_ms,
            error_code=result.error_code,
        ))
    return articles, source_runs

