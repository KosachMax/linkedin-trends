"""
Hacker News collector — Algolia Search API (публичный, без ключей).
"""
import time
import requests
from dataclasses import dataclass
from typing import Optional
from config import SOURCES, TOPICS

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"


@dataclass
class Post:
    source: str
    title: str
    url: str
    score: int
    comments: int
    text: str = ""


def collect(cfg: Optional[dict] = None) -> list[Post]:
    cfg = cfg or SOURCES["hackernews"]
    all_posts: list[Post] = []
    seen_ids: set[str] = set()

    for topic in TOPICS:
        day_ago = int(time.time()) - 24 * 3600
        params = {
            "query": topic,
            "tags": "story",
            "numericFilters": f"points>={cfg['min_score']},created_at_i>{day_ago}",
            "hitsPerPage": cfg["post_limit"],
        }

        try:
            resp = requests.get(ALGOLIA_URL, params=params, timeout=10)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
        except Exception as e:
            print(f"  [hn] Ошибка запроса '{topic}': {e}")
            continue

        for hit in hits:
            story_id = hit.get("objectID", "")
            if story_id in seen_ids:
                continue
            seen_ids.add(story_id)

            all_posts.append(Post(
                source="hackernews",
                title=hit.get("title", ""),
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={story_id}",
                score=hit.get("points", 0),
                comments=hit.get("num_comments", 0),
                text=hit.get("story_text") or "",
            ))

        print(f"  [hn] '{topic}' → {len(hits)} постов")

    return all_posts
