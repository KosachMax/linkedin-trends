import html
import re
from datetime import UTC

from trends.domain.ids import canonicalize_url, stable_article_id
from trends.domain.models import Article, RawArticle


def normalize_text(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", value).strip()


def normalize_title(value: str) -> str:
    return normalize_text(value).casefold()


def normalize_article(raw: RawArticle) -> Article:
    url = canonicalize_url(str(raw.url))
    published_at = raw.published_at
    if published_at and published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    return Article(
        id=raw.id or stable_article_id(raw.source_id, url),
        source_id=raw.source_id,
        source_name=raw.source_name,
        canonical_url=url,
        title=normalize_text(raw.title),
        normalized_title=normalize_title(raw.title),
        excerpt=normalize_text(raw.excerpt) if raw.excerpt else None,
        published_at=published_at,
        collected_at=raw.collected_at,
        language=raw.language,
        topic_hints=[item.casefold() for item in raw.topic_hints],
        engagement=raw.engagement,
    )


def normalize_articles(raw_articles: list[RawArticle]) -> list[Article]:
    return [normalize_article(article) for article in raw_articles]
