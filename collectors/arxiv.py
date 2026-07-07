"""
ArXiv collector — свежие статьи по AI/ML/CS через Atom API.
Не требует ключей.
"""
import feedparser
from dataclasses import dataclass
from typing import Optional
from config import SOURCES

BASE_URL = (
    "https://export.arxiv.org/api/query"
    "?search_query=cat:{cat}"
    "&sortBy=submittedDate&sortOrder=descending"
    "&max_results={limit}"
)


@dataclass
class Post:
    source: str
    title: str
    url: str
    score: int
    comments: int
    text: str = ""


def collect(cfg: Optional[dict] = None) -> list[Post]:
    cfg = cfg or SOURCES.get("arxiv", {})
    categories = cfg.get("categories", ["cs.AI", "cs.LG", "cs.CL"])
    post_limit = cfg.get("post_limit", 10)

    posts: list[Post] = []
    seen: set[str] = set()

    for cat in categories:
        url = BASE_URL.format(cat=cat, limit=post_limit)
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries:
                link = entry.get("link", "")
                if not link or link in seen:
                    continue
                seen.add(link)
                title = " ".join(entry.get("title", "").split())
                summary = " ".join(entry.get("summary", "").split())[:300]
                posts.append(Post(
                    source=f"arxiv/{cat}",
                    title=title,
                    url=link,
                    score=5,
                    comments=0,
                    text=summary,
                ))
                count += 1
            print(f"  [arxiv] {cat} → {count} статей")
        except Exception as e:
            print(f"  [arxiv] Ошибка {cat}: {e}")

    return posts
