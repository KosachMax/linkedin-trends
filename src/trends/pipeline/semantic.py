from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime

from trends.domain.models import Article, DedupeConfig, DigestEvent

from .dedupe import title_similarity


@dataclass
class SemanticStats:
    embedding_model: str | None = None
    semantic_candidate_pairs: int = 0
    candidate_bundles: int = 0
    largest_bundle: int = 0
    degraded: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def article_embedding_text(article: Article) -> str:
    timestamp = article.published_at or article.collected_at
    return (
        f"title: {article.title} | text: {article.excerpt or ''} | "
        f"published_at: {timestamp.isoformat()}"
    )


def event_embedding_text(event: DigestEvent) -> str:
    identity = event.identity
    identity_text = ""
    if identity:
        identity_text = (
            f" | event_type: {identity.event_type}"
            f" | entities: {', '.join(identity.primary_entities)}"
            f" | geographies: {', '.join(identity.geographies)}"
        )
    return f"title: {event.title} | text: {event.brief}{identity_text}"


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def similarity_matrix(vectors: list[list[float]]) -> list[list[float]]:
    matrix = [
        [1.0 if left == right else 0.0 for right in range(len(vectors))]
        for left in range(len(vectors))
    ]
    for left in range(len(vectors)):
        for right in range(left + 1, len(vectors)):
            score = cosine_similarity(vectors[left], vectors[right])
            matrix[left][right] = score
            matrix[right][left] = score
    return matrix


def lexical_similarity_matrix(articles: list[Article]) -> list[list[float]]:
    matrix = [
        [1.0 if left == right else 0.0 for right in range(len(articles))]
        for left in range(len(articles))
    ]
    for left in range(len(articles)):
        for right in range(left + 1, len(articles)):
            score = title_similarity(articles[left], articles[right])
            matrix[left][right] = score
            matrix[right][left] = score
    return matrix


def _published(article: Article) -> datetime:
    return article.published_at or article.collected_at


def _within_window(left: Article, right: Article, lookback_hours: int) -> bool:
    return abs((_published(left) - _published(right)).total_seconds()) <= (
        lookback_hours * 3600
    )


def build_candidate_bundles(
    articles: list[Article],
    matrix: list[list[float]],
    rules: DedupeConfig,
) -> tuple[list[list[Article]], SemanticStats]:
    """Build conservative complete-link bundles for subsequent AI verification."""
    if len(matrix) != len(articles) or any(
        len(row) != len(articles) for row in matrix
    ):
        raise ValueError("similarity matrix shape does not match article count")

    neighbor_sets: list[set[int]] = []
    for left, article in enumerate(articles):
        candidates = [
            (matrix[left][right], right)
            for right in range(len(articles))
            if right != left
            and _within_window(article, articles[right], rules.lookback_hours)
            and matrix[left][right] >= rules.candidate_similarity
        ]
        candidates.sort(reverse=True)
        neighbor_sets.append({right for _, right in candidates[: rules.max_neighbors]})

    candidate_pairs = {
        tuple(sorted((left, right)))
        for left, neighbors in enumerate(neighbor_sets)
        for right in neighbors
    }

    bundles: list[list[int]] = []
    order = sorted(
        range(len(articles)),
        key=lambda index: (_published(articles[index]), articles[index].id),
        reverse=True,
    )
    for index in order:
        best_bundle: list[int] | None = None
        best_score = -1.0
        for bundle in bundles:
            if len(bundle) >= rules.max_bundle_size:
                continue
            if not all(
                _within_window(
                    articles[index], articles[member], rules.lookback_hours
                )
                and matrix[index][member] >= rules.candidate_similarity
                for member in bundle
            ):
                continue
            if not any(
                tuple(sorted((index, member))) in candidate_pairs
                for member in bundle
            ):
                continue
            score = sum(matrix[index][member] for member in bundle) / len(bundle)
            if score > best_score:
                best_score = score
                best_bundle = bundle
        if best_bundle is None:
            bundles.append([index])
        else:
            best_bundle.append(index)

    result = [[articles[index] for index in bundle] for bundle in bundles]
    multi = [bundle for bundle in result if len(bundle) > 1]
    stats = SemanticStats(
        semantic_candidate_pairs=len(candidate_pairs),
        candidate_bundles=len(multi),
        largest_bundle=max((len(bundle) for bundle in result), default=0),
    )
    return result, stats


def nearest_event_pairs(
    incoming: list[DigestEvent],
    existing: list[DigestEvent],
    incoming_vectors: list[list[float]],
    existing_vectors: list[list[float]],
    rules: DedupeConfig,
    *,
    max_neighbors: int = 3,
) -> list[tuple[DigestEvent, DigestEvent, float]]:
    pairs: list[tuple[DigestEvent, DigestEvent, float]] = []
    for candidate, candidate_vector in zip(incoming, incoming_vectors, strict=True):
        neighbors = []
        for old, old_vector in zip(existing, existing_vectors, strict=True):
            age_hours = abs(
                (candidate.updated_at - old.updated_at).total_seconds()
            ) / 3600
            if age_hours > rules.lookback_hours:
                continue
            score = cosine_similarity(candidate_vector, old_vector)
            if score >= rules.candidate_similarity:
                neighbors.append((score, old))
        neighbors.sort(key=lambda item: item[0], reverse=True)
        pairs.extend(
            (candidate, old, score) for score, old in neighbors[:max_neighbors]
        )
    return pairs
