from datetime import UTC, datetime

from trends.domain.models import Article, DigestProfile


def cluster_score(cluster: list[Article], profile: DigestProfile, impact: int) -> float:
    now = datetime.now(UTC)
    newest = max((item.published_at or item.collected_at) for item in cluster)
    age_hours = max(0.0, (now - newest).total_seconds() / 3600)
    freshness = max(0.0, 1.0 - age_hours / 72)
    diversity = min(1.0, len({item.source_id for item in cluster}) / 4)
    relevance_terms = {hint for item in cluster for hint in item.topic_hints}
    wanted = {term.casefold() for term in profile.topic.include_any}
    relevance = min(1.0, len(relevance_terms & wanted) / 3)
    engagement_values = [item.engagement or 0 for item in cluster]
    engagement = min(1.0, max(engagement_values, default=0) / 1000)
    weights = profile.ranking
    return (
        weights.get("impact", 0.2) * impact / 10
        + weights.get("source_diversity", 0.25) * diversity
        + weights.get("recency", 0.25) * freshness
        + weights.get("topic_relevance", 0.25) * relevance
        + weights.get("engagement", 0.05) * engagement
    )

