"""
Medium collector — RSS feeds по тегам.
Не требует ключей.
"""
import re
import feedparser
from dataclasses import dataclass
from typing import Optional
from config import SOURCES


@dataclass
class Post:
    source: str
    title: str
    url: str
    score: int
    comments: int
    text: str = ""


def collect(cfg: Optional[dict] = None) -> list[Post]:
    cfg = cfg or SOURCES.get("medium", {})
    tags = cfg.get("tags", [
        "python", "machine-learning", "artificial-intelligence",
        "software-engineering", "llm", "data-science",
    ])
    post_limit = cfg.get("post_limit", 8)

    posts: list[Post] = []
    seen: set[str] = set()

    for tag in tags:
        url = f"https://medium.com/feed/tag/{tag}"
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries[:post_limit]:
                link = entry.get("link", "")
                if not link or link in seen:
                    continue
                seen.add(link)
                title = entry.get("title", "").strip()
                raw_summary = entry.get("summary", "")
                summary = re.sub(r"<[^>]+>", " ", raw_summary).strip()[:300]
                posts.append(Post(
                    source=f"medium/{tag}",
                    title=title,
                    url=link,
                    score=5,
                    comments=0,
                    text=summary,
                ))
                count += 1
            print(f"  [medium] #{tag} → {count} постов")
        except Exception as e:
            print(f"  [medium] Ошибка #{tag}: {e}")

    return posts
