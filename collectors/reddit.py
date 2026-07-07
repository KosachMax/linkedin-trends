"""
Reddit collector.

Если заданы REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET — использует PRAW OAuth
(работает с любых IP, в т.ч. GitHub Actions).
Без них — публичный JSON API (заблокирован GitHub Actions IP с 2023 года).
"""
import os
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


def _fetch_praw(subreddit_name: str, cfg: dict) -> list[Post]:
    import praw
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent="trends-aggregator/1.0",
    )
    posts = []
    try:
        for submission in reddit.subreddit(subreddit_name).top(
            time_filter=cfg["time_filter"], limit=cfg["post_limit"]
        ):
            if submission.score < cfg["min_score"]:
                continue
            posts.append(Post(
                source=f"reddit/r/{subreddit_name}",
                title=submission.title,
                url=f"https://reddit.com{submission.permalink}",
                score=submission.score,
                comments=submission.num_comments,
                text=(submission.selftext or "")[:500],
            ))
    except Exception as e:
        print(f"  [reddit] PRAW ошибка {subreddit_name}: {e}")
    return posts


def _fetch_public(subreddit: str, cfg: dict) -> list[Post]:
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
            text=d.get("selftext", "")[:500],
        ))
    time.sleep(1)
    return posts


def collect(cfg: Optional[dict] = None) -> list[Post]:
    cfg = cfg or SOURCES["reddit"]
    use_praw = bool(
        os.environ.get("REDDIT_CLIENT_ID") and os.environ.get("REDDIT_CLIENT_SECRET")
    )

    if use_praw:
        print("  [reddit] OAuth via PRAW")
    else:
        print("  [reddit] Публичный API (может быть заблокирован с CI-серверов)")

    all_posts: list[Post] = []
    for subreddit in cfg["subreddits"]:
        print(f"  [reddit] r/{subreddit}...")
        posts = _fetch_praw(subreddit, cfg) if use_praw else _fetch_public(subreddit, cfg)
        all_posts.extend(posts)
        print(f"    → {len(posts)} постов")

    return all_posts
