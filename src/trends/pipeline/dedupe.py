from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import asdict, dataclass

from rapidfuzz.fuzz import token_set_ratio

from trends.domain.models import Article


TOKEN_RE = re.compile(r"[\w'-]+", flags=re.UNICODE)


@dataclass
class DedupeStats:
    input_articles: int = 0
    exact_url_duplicates: int = 0
    same_source_near_duplicates: int = 0
    output_articles: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def _article_text(article: Article) -> str:
    return f"{article.normalized_title} {(article.excerpt or '').casefold()}".strip()


def simhash(value: str, bits: int = 64) -> int:
    weights = [0] * bits
    tokens = Counter(TOKEN_RE.findall(value.casefold()))
    for token, frequency in tokens.items():
        digest = int.from_bytes(
            hashlib.blake2b(token.encode("utf-8"), digest_size=bits // 8).digest(),
            "big",
        )
        for index in range(bits):
            weights[index] += frequency if digest & (1 << index) else -frequency
    result = 0
    for index, weight in enumerate(weights):
        if weight >= 0:
            result |= 1 << index
    return result


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def dedupe_articles(
    articles: list[Article],
    *,
    max_hamming_distance: int = 3,
    same_source_window_hours: int = 24,
) -> tuple[list[Article], DedupeStats]:
    """Remove exact and near copies within a source, preserving cross-source proof."""
    stats = DedupeStats(input_articles=len(articles))
    seen_urls: set[tuple[str, str]] = set()
    seen_by_source: dict[str, list[tuple[Article, int]]] = {}
    result: list[Article] = []

    for article in articles:
        url_key = (article.source_id, str(article.canonical_url))
        if url_key in seen_urls:
            stats.exact_url_duplicates += 1
            continue

        fingerprint = simhash(_article_text(article))
        timestamp = article.published_at or article.collected_at
        duplicate = False
        for previous, previous_fingerprint in seen_by_source.get(article.source_id, []):
            previous_timestamp = previous.published_at or previous.collected_at
            age_hours = abs((timestamp - previous_timestamp).total_seconds()) / 3600
            if age_hours <= same_source_window_hours and hamming_distance(
                fingerprint, previous_fingerprint
            ) <= max_hamming_distance:
                duplicate = True
                break
        if duplicate:
            stats.same_source_near_duplicates += 1
            continue

        seen_urls.add(url_key)
        seen_by_source.setdefault(article.source_id, []).append((article, fingerprint))
        result.append(article)

    stats.output_articles = len(result)
    return result, stats


def exact_dedupe(articles: list[Article]) -> list[Article]:
    return dedupe_articles(articles)[0]


def title_similarity(left: Article, right: Article) -> float:
    return token_set_ratio(left.normalized_title, right.normalized_title) / 100


def candidate_pairs(articles: list[Article], threshold: float = 0.72):
    for index, left in enumerate(articles):
        for right in articles[index + 1 :]:
            score = title_similarity(left, right)
            if score >= threshold:
                yield left, right, score
