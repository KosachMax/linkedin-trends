"""
Dev.to collector — публичный REST API.
API key опционален (повышает лимит запросов).
"""
import os
import requests
from dataclasses import dataclass
from typing import Optional
from config import SOURCES

BASE_URL = "https://dev.to/api/articles"


@dataclass
class Post:
    source: str
    title: str
    url: str
    score: int       # reactions_count
    comments: int
    text: str = ""


def collect(cfg: Optional[dict] = None) -> list[Post]:
    cfg = cfg or SOURCES["devto"]
    all_posts: list[Post] = []
    seen_ids: set[int] = set()

    api_key = os.getenv("DEVTO_API_KEY", "")
    headers = {"api-key": api_key} if api_key else {}

    for tag in cfg["tags"]:
        params = {
            "tag": tag,
            "per_page": cfg["post_limit"],
            "top": 1,  # топ за последние сутки
        }

        try:
            resp = requests.get(BASE_URL, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            articles = resp.json()
        except Exception as e:
            print(f"  [devto] Ошибка тег '{tag}': {e}")
            continue

        count = 0
        for art in articles:
            article_id = art.get("id")
            reactions = art.get("public_reactions_count", 0)

            if article_id in seen_ids:
                continue
            if reactions < cfg["min_reactions"]:
                continue

            seen_ids.add(article_id)
            all_posts.append(Post(
                source=f"dev.to/t/{tag}",
                title=art.get("title", ""),
                url=art.get("url", ""),
                score=reactions,
                comments=art.get("comments_count", 0),
                text=art.get("description") or "",
            ))
            count += 1

        print(f"  [devto] #{tag} → {count} постов")

    return all_posts
