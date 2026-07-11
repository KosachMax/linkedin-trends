import re

from trends.domain.models import Article, DigestProfile


def _matches(term: str, haystack: str) -> bool:
    normalized = term.casefold().strip()
    if not normalized:
        return False
    if re.fullmatch(r"[\w-]+", normalized):
        return re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", haystack) is not None
    return normalized in haystack


def article_matches_digest(article: Article, profile: DigestProfile) -> bool:
    haystack = " ".join(
        [article.title, article.excerpt or "", *article.topic_hints]
    ).casefold()
    if any(_matches(term, haystack) for term in profile.topic.exclude_any):
        return False
    return any(_matches(term, haystack) for term in profile.topic.include_any)


def select_for_digest(articles: list[Article], profile: DigestProfile) -> list[Article]:
    return [article for article in articles if article_matches_digest(article, profile)]
