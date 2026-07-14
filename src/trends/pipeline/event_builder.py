from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime

from trends.ai.dedupe_service import DedupeService
from trends.ai.gemini import GeminiProvider
from trends.ai.service import EventSynthesisService
from trends.domain.enums import EventStatus
from trends.domain.ids import slugify
from trends.domain.models import (
    Article,
    DigestEvent,
    DigestProfile,
    EventIdentity,
    Fact,
)

from .cluster import cluster_articles
from .semantic import (
    article_embedding_text,
    build_candidate_bundles,
    lexical_similarity_matrix,
    similarity_matrix,
)


def stable_event_id(digest_id: str, articles: list[Article]) -> str:
    primary = min(
        articles,
        key=lambda article: (
            article.published_at or article.collected_at,
            article.id,
        ),
    )
    fingerprint = f"{digest_id}:{primary.id}".encode()
    return f"{digest_id}-{hashlib.sha256(fingerprint).hexdigest()[:16]}"


def fallback_text(value: str, minimum: int) -> str:
    suffix = (
        " Сводка создана автоматически из доступных заголовков и описаний; "
        "дополнительные сведения появятся после подтверждения источниками."
    )
    result = value.strip()
    while len(result) < minimum:
        result = f"{result}{suffix}"
    return result


def _error(stage: str, error: Exception) -> str:
    detail = " ".join(str(error).split())[:180]
    return f"{stage}:{type(error).__name__}:{detail}" if detail else (
        f"{stage}:{type(error).__name__}"
    )


async def partition_articles(
    articles: list[Article],
    profile: DigestProfile,
    provider: GeminiProvider | None,
    dedupe_ai: DedupeService | None,
    metrics: dict[str, object],
) -> list[list[Article]]:
    if not articles:
        return []
    if provider is None or dedupe_ai is None:
        metrics["degraded"] = True
        metrics.setdefault("errors", []).append("ai_unavailable")
        return cluster_articles(articles)

    try:
        vectors = await provider.embed(
            [article_embedding_text(article) for article in articles]
        )
        if len(vectors) != len(articles):
            raise ValueError(
                f"embedding provider returned {len(vectors)} vectors for "
                f"{len(articles)} articles"
            )
        dimensions = {len(vector) for vector in vectors}
        if dimensions == {0} or len(dimensions) != 1:
            raise ValueError("embedding vectors must have one non-zero dimension")
        matrix = similarity_matrix(vectors)
    except Exception as error:
        matrix = lexical_similarity_matrix(articles)
        metrics["degraded"] = True
        metrics.setdefault("errors", []).append(_error("embeddings", error))

    bundles, semantic_stats = build_candidate_bundles(
        articles, matrix, profile.dedupe
    )
    semantic_stats.embedding_model = (
        provider.embedding_model if not metrics.get("degraded") else None
    )
    semantic_stats.degraded = bool(metrics.get("degraded"))
    metrics.update(semantic_stats.to_dict())
    semaphore = asyncio.Semaphore(3)

    async def verify(bundle: list[Article]) -> list[list[Article]]:
        if len(bundle) == 1:
            return [bundle]
        try:
            async with semaphore:
                partition = await dedupe_ai.partition_articles(bundle)
            by_id = {article.id: article for article in bundle}
            metrics["ai_partitions"] = int(metrics.get("ai_partitions", 0)) + 1
            metrics["ai_splits"] = int(metrics.get("ai_splits", 0)) + max(
                0, len(partition.groups) - 1
            )
            return [
                [by_id[article_id] for article_id in group.article_ids]
                for group in partition.groups
            ]
        except Exception as error:
            metrics["degraded"] = True
            metrics.setdefault("errors", []).append(_error("partition", error))
            return cluster_articles(
                bundle,
                threshold=max(0.72, profile.dedupe.candidate_similarity),
            )

    verified = await asyncio.gather(*(verify(bundle) for bundle in bundles))
    clusters = [
        cluster
        for bundle_clusters in verified
        for cluster in bundle_clusters
    ]
    return sorted(
        clusters,
        key=lambda cluster: max(
            item.published_at or item.collected_at for item in cluster
        ),
        reverse=True,
    )


async def build_event(
    profile: DigestProfile,
    cluster: list[Article],
    started: datetime,
    ai: EventSynthesisService | None,
    *,
    minimum_sources: int | None = None,
) -> DigestEvent:
    primary = cluster[0]
    independent_sources = len({item.source_id for item in cluster})
    if ai:
        synthesis = await ai.synthesize(
            cluster,
            minimum_sources=minimum_sources
            or profile.sources.min_independent_sources,
        )
        title = synthesis.title
        brief = synthesis.brief
        context = synthesis.context
        why = synthesis.why_it_matters
        category = synthesis.category
        importance = synthesis.impact
        facts = [
            Fact(text=fact.text, article_ids=fact.article_ids)
            for fact in synthesis.facts
        ]
        identity = EventIdentity.model_validate(synthesis.identity.model_dump())
        status = EventStatus(synthesis.status)
    else:
        title = primary.title
        brief = fallback_text(primary.excerpt or primary.title, 220)
        context = fallback_text(primary.excerpt or primary.title, 220)
        why = fallback_text(f"Событие затрагивает тему «{profile.title}».", 170)
        category = primary.topic_hints[-1] if primary.topic_hints else "news"
        importance = min(10, 5 + independent_sources)
        facts = [
            Fact(
                text=primary.excerpt or primary.title,
                article_ids=[primary.id],
            )
        ]
        status = EventStatus.NEW
        identity = EventIdentity(
            event_type=slugify(category).replace("-", "_") or "news_event",
            occurred_at=primary.published_at,
        )

    return DigestEvent(
        id=stable_event_id(profile.id, cluster),
        slug=slugify(title),
        title=title,
        brief=brief,
        context=context,
        why_it_matters=why,
        importance=importance,
        status=status,
        category=category,
        article_ids=[article.id for article in cluster],
        facts=facts,
        identity=identity,
        first_seen_at=min(
            item.published_at or item.collected_at for item in cluster
        ),
        updated_at=started,
    )
