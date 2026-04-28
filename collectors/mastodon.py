"""
Mastodon trending statuses collector — tech-инстанс Hachyderm по умолчанию.
Доступ без токена: эндпоинт /api/v1/trends/statuses публичный.
"""
import re
from dataclasses import dataclass
from typing import Optional

import requests

from config import SOURCES, TOPICS

HEADERS = {"User-Agent": "trends-aggregator/1.0 (personal research bot)"}

TECH_HASHTAGS = {
    "ai", "ml", "llm", "python", "programming", "softwaredev", "softwareengineering",
    "machinelearning", "artificialintelligence", "opensource", "devops", "backend",
    "rust", "golang", "typescript", "javascript", "kubernetes", "docker",
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class Post:
    source: str
    title: str
    url: str
    score: int
    comments: int
    text: str = ""


def _strip_html(s: str) -> str:
    return _HTML_TAG_RE.sub("", s or "").strip()


def _is_tech(status: dict) -> bool:
    tags = {t.get("name", "").lower() for t in status.get("tags", [])}
    if tags & TECH_HASHTAGS:
        return True
    text = _strip_html(status.get("content", "")).lower()
    if any(t in text for t in TOPICS):
        return True
    return False


def collect(cfg: Optional[dict] = None) -> list[Post]:
    cfg = cfg or SOURCES["mastodon"]
    instance = cfg["instance"]
    url = f"https://{instance}/api/v1/trends/statuses"
    params = {"limit": cfg["post_limit"]}

    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json()
    except Exception as e:
        print(f"  [mastodon] error: {e}")
        return []

    posts: list[Post] = []
    for s in items:
        if not _is_tech(s):
            continue
        favs = s.get("favourites_count", 0)
        boosts = s.get("reblogs_count", 0)
        score = favs + boosts * 2
        if score < cfg["min_score"]:
            continue
        text = _strip_html(s.get("content", ""))
        posts.append(Post(
            source=f"mastodon/{instance.split('.')[0]}",
            title=text[:120],
            url=s.get("url", ""),
            score=score,
            comments=s.get("replies_count", 0),
            text=text[:500],
        ))

    print(f"  [mastodon] → {len(posts)} постов")
    return posts
