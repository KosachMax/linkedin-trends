"""
Lobste.rs collector — community-driven tech aggregator (HN-альтернатива).
"""
from dataclasses import dataclass
from typing import Optional

import requests

from config import SOURCES

URL = "https://lobste.rs/hottest.json"
HEADERS = {"User-Agent": "trends-aggregator/1.0 (personal research bot)"}


@dataclass
class Post:
    source: str
    title: str
    url: str
    score: int
    comments: int
    text: str = ""


def collect(cfg: Optional[dict] = None) -> list[Post]:
    cfg = cfg or SOURCES["lobsters"]

    try:
        resp = requests.get(URL, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        items = resp.json()
    except Exception as e:
        print(f"  [lobsters] error: {e}")
        return []

    posts: list[Post] = []
    for item in items[: cfg["post_limit"]]:
        score = item.get("score", 0)
        if score < cfg["min_score"]:
            continue
        posts.append(Post(
            source="lobsters",
            title=item.get("title", ""),
            url=item.get("url") or item.get("short_id_url", ""),
            score=score,
            comments=item.get("comment_count", 0),
            text=(item.get("description") or "")[:500],
        ))

    print(f"  [lobsters] → {len(posts)} постов")
    return posts
