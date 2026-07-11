from rapidfuzz.fuzz import token_set_ratio

from trends.domain.models import Article


def exact_dedupe(articles: list[Article]) -> list[Article]:
    seen: set[str] = set()
    result: list[Article] = []
    for article in articles:
        key = str(article.canonical_url)
        if key not in seen:
            seen.add(key)
            result.append(article)
    return result


def title_similarity(left: Article, right: Article) -> float:
    return token_set_ratio(left.normalized_title, right.normalized_title) / 100


def candidate_pairs(articles: list[Article], threshold: float = 0.72):
    for index, left in enumerate(articles):
        for right in articles[index + 1 :]:
            score = title_similarity(left, right)
            if score >= threshold:
                yield left, right, score

