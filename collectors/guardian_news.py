"""
Guardian collector — The Guardian API (free tier).
Установи GUARDIAN_API_KEY в .env, либо используется публичный ключ 'test'.
"""
import os
import requests
from collectors.rss_news import NewsItem
from config import NEWS_PER_SOURCE

BASE_URL = "https://content.guardianapis.com/search"


def collect() -> list[NewsItem]:
    api_key = os.environ.get("GUARDIAN_API_KEY", "test")
    params = {
        "api-key": api_key,
        "section": "world,politics,business,environment,us-news,uk-news",
        "order-by": "newest",
        "page-size": NEWS_PER_SOURCE,
        "show-fields": "trailText",
    }

    try:
        resp = requests.get(BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("response", {}).get("results", [])
    except Exception as e:
        print(f"  [guardian] Ошибка: {e}")
        return []

    items = []
    for r in results:
        items.append(NewsItem(
            source="The Guardian",
            title=r.get("webTitle", "").strip(),
            url=r.get("webUrl", ""),
            summary=r.get("fields", {}).get("trailText", "")[:400].strip(),
            published=r.get("webPublicationDate", ""),
            language="en",
        ))

    print(f"  [guardian] → {len(items)} новостей")
    return items
