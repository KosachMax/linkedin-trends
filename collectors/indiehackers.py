"""
Indie Hackers collector — посты сообщества через RSS.
Не требует ключей.
"""
import re
import feedparser
from dataclasses import dataclass
from typing import Optional
from config import SOURCES

FEED_URL = "https://www.indiehackers.com/feed"


@dataclass
class Post:
    source: str
    title: str
    url: str
    score: int
    comments: int
    text: str = ""


def collect(cfg: Optional[dict] = None) -> list[Post]:
    cfg = cfg or SOURCES.get("indiehackers", {})
    post_limit = cfg.get("post_limit", 20)

    posts: list[Post] = []
    try:
        feed = feedparser.parse(FEED_URL)
        for entry in feed.entries[:post_limit]:
            link = entry.get("link", "")
            if not link:
                continue
            title = entry.get("title", "").strip()
            raw = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")
            summary = re.sub(r"<[^>]+>", " ", raw).strip()[:300]
            posts.append(Post(
                source="indiehackers",
                title=title,
                url=link,
                score=5,
                comments=0,
                text=summary,
            ))
        print(f"  [indiehackers] → {len(posts)} постов")
    except Exception as e:
        print(f"  [indiehackers] Ошибка: {e}")

    return posts
