"""
Hacker News collector — Algolia Search API (публичный, без ключей).
Использует /search_by_date с локальной фильтрацией, чтобы избежать
URL-encoding проблем с numericFilters (>/%3E).
"""
import time
import requests
from dataclasses import dataclass
from typing import Optional
from config import SOURCES, TOPICS


ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"


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
    min_score = cfg.get("min_score", 50)
    post_limit = cfg.get("post_limit", 30)
    all_posts: list[Post] = []
    seen_ids: set[str] = set()

    for topic in TOPICS:
        day_ago = int(time.time()) - 24 * 3600
        params = {
            "query": topic,
            "tags": "story",
            "hitsPerPage": post_limit,
        }

        try:
            resp = requests.get(ALGOLIA_URL, params=params, timeout=10)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
        except Exception as e:
            print(f"  [hn] Ошибка запроса '{topic}': {e}")
            continue

        accepted = 0
        for hit in hits:
            story_id = hit.get("objectID", "")
            if story_id in seen_ids:
                continue
            if hit.get("points", 0) < min_score:
                continue
            if hit.get("created_at_i", 0) < day_ago:
                continue
            seen_ids.add(story_id)
            accepted += 1

            all_posts.append(Post(
                source="hackernews",
                title=hit.get("title", ""),
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={story_id}",
                score=hit.get("points", 0),
                comments=hit.get("num_comments", 0),
                text=hit.get("story_text") or "",
            ))

        print(f"  [hn] '{topic}' → {accepted} постов (из {len(hits)} fetched)")

    return all_posts
