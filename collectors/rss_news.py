"""
RSS collector — парсит новостные ленты Reuters, BBC, Al Jazeera, RBC.
"""
import feedparser
from dataclasses import dataclass
from config import RSS_FEEDS


@dataclass
class NewsItem:
    source: str
    title: str
    url: str
    summary: str
    published: str


def collect() -> list[NewsItem]:
    items: list[NewsItem] = []
    seen_urls: set[str] = set()

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            count = 0
            for entry in feed.entries:
                url = entry.get("link", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                items.append(NewsItem(
                    source=source_name,
                    title=entry.get("title", "").strip(),
                    url=url,
                    summary=(entry.get("summary") or entry.get("description") or "")[:400].strip(),
                    published=entry.get("published", ""),
                ))
                count += 1
            print(f"  [rss] {source_name} → {count} новостей")
        except Exception as e:
            print(f"  [rss] Ошибка {source_name}: {e}")

    return items
