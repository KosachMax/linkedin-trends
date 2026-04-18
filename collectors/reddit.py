"""
Reddit collector — использует публичный JSON API (без OAuth, без ключей).
"""
import time
import requests
from dataclasses import dataclass
from typing import Optional
from config import SOURCES

HEADERS = {"User-Agent": "trends-aggregator/1.0 (personal research bot)"}


@dataclass
class Post:
    source: str
    title: str
    url: str
    score: int
    comments: int
    text: str = ""


def fetch_subreddit(subreddit: str, cfg: dict) -> list[Post]:
    url = f"https://www.reddit.com/r/{subreddit}/top.json"
    params = {"limit": cfg["post_limit"], "t": cfg["time_filter"]}

    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [reddit] Ошибка {subreddit}: {e}")
        return []

    posts = []
    for item in data.get("data", {}).get("children", []):
        d = item["data"]
        score = d.get("score", 0)
        if score < cfg["min_score"]:
            continue
        posts.append(Post(
            source=f"reddit/r/{subreddit}",
            title=d.get("title", ""),
            url=f"https://reddit.com{d.get('permalink', '')}",
            score=score,
            comments=d.get("num_comments", 0),
            text=d.get("selftext", "")[:500],  # первые 500 символов body
        ))

    time.sleep(1)  # уважаем rate limit Reddit
    return posts


def collect(cfg: Optional[dict] = None) -> list[Post]:
    cfg = cfg or SOURCES["reddit"]
    all_posts: list[Post] = []

    for subreddit in cfg["subreddits"]:
        print(f"  [reddit] r/{subreddit}...")
        posts = fetch_subreddit(subreddit, cfg)
        all_posts.extend(posts)
        print(f"    → {len(posts)} постов")

    return all_posts
