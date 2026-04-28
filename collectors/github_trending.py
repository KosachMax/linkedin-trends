"""
GitHub Trending collector — репозитории с максимальным приростом звёзд за сутки.
Источник: GitHub Search API. С `GITHUB_TOKEN` лимит выше (5000 req/hr vs 60).
"""
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import requests

from config import SOURCES

BASE_URL = "https://api.github.com/search/repositories"


@dataclass
class Post:
    source: str
    title: str
    url: str
    score: int
    comments: int
    text: str = ""


def collect(cfg: Optional[dict] = None) -> list[Post]:
    cfg = cfg or SOURCES["github"]
    since = (date.today() - timedelta(days=cfg["since_days"])).strftime("%Y-%m-%d")

    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = {
        "q": f"created:>{since}",
        "sort": "stars",
        "order": "desc",
        "per_page": cfg["post_limit"],
    }

    try:
        resp = requests.get(BASE_URL, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except Exception as e:
        print(f"  [github] error: {e}")
        return []

    posts: list[Post] = []
    for r in items:
        stars = r.get("stargazers_count", 0)
        if stars < cfg["min_stars"]:
            continue
        full_name = r.get("full_name", "")
        description = r.get("description") or ""
        posts.append(Post(
            source="github",
            title=f"{full_name} — {description}" if description else full_name,
            url=r.get("html_url", ""),
            score=stars,
            comments=r.get("open_issues_count", 0),
            text=description[:500],
        ))

    print(f"  [github] → {len(posts)} репозиториев")
    return posts
