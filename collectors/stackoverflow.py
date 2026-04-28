"""
Stack Overflow Hot Questions collector — Stack Exchange API.
Без ключа: 300 req/day на IP.
"""
import re
from dataclasses import dataclass
from typing import Optional

import requests

from config import SOURCES

URL = "https://api.stackexchange.com/2.3/questions"
HEADERS = {"User-Agent": "trends-aggregator/1.0 (personal research bot)"}

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


def collect(cfg: Optional[dict] = None) -> list[Post]:
    cfg = cfg or SOURCES["stackoverflow"]
    posts: list[Post] = []
    seen: set[int] = set()

    for tag in cfg["tags"]:
        params = {
            "order": "desc",
            "sort": "hot",
            "site": "stackoverflow",
            "tagged": tag,
            "pagesize": cfg["post_limit"],
            "filter": "withbody",
        }
        try:
            resp = requests.get(URL, headers=HEADERS, params=params, timeout=10)
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except Exception as e:
            print(f"  [stackoverflow] error '{tag}': {e}")
            continue

        for q in items:
            qid = q.get("question_id")
            if qid in seen:
                continue
            seen.add(qid)
            score = q.get("score", 0)
            views = q.get("view_count", 0)
            engagement = score + views // 100
            if engagement < cfg["min_score"]:
                continue
            body = _strip_html(q.get("body", ""))
            posts.append(Post(
                source="stackoverflow",
                title=q.get("title", ""),
                url=q.get("link", ""),
                score=engagement,
                comments=q.get("answer_count", 0),
                text=body[:500],
            ))

    print(f"  [stackoverflow] → {len(posts)} вопросов")
    return posts
