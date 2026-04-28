"""
LinkedIn Trends Aggregator + World News
Запуск: python main.py [--mode tech|news|all]
"""
import os
import sys
import argparse
from pathlib import Path
from datetime import date
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

import config
from collectors import reddit, hackernews, devto
from collectors import github_trending, lobsters, mastodon, stackoverflow
from collectors import rss_news, guardian_news
from analyzer.llm_analyzer import analyze as analyze_tech
from analyzer.news_analyzer import analyze as analyze_news
from output.obsidian_writer import save as save_tech
from output.news_writer import save as save_news
from config import SOURCES


def collect_tech() -> list:
    all_posts = []

    if SOURCES["reddit"]["enabled"]:
        print("\n📥 Reddit...")
        posts = reddit.collect()
        print(f"  Итого: {len(posts)} постов")
        all_posts.extend(posts)

    if SOURCES["hackernews"]["enabled"]:
        print("\n📥 Hacker News...")
        posts = hackernews.collect()
        print(f"  Итого: {len(posts)} постов")
        all_posts.extend(posts)

    if SOURCES["devto"]["enabled"]:
        print("\n📥 Dev.to...")
        posts = devto.collect()
        print(f"  Итого: {len(posts)} постов")
        all_posts.extend(posts)

    if SOURCES.get("github", {}).get("enabled"):
        print("\n📥 GitHub Trending...")
        posts = github_trending.collect()
        print(f"  Итого: {len(posts)} постов")
        all_posts.extend(posts)

    if SOURCES.get("lobsters", {}).get("enabled"):
        print("\n📥 Lobste.rs...")
        posts = lobsters.collect()
        print(f"  Итого: {len(posts)} постов")
        all_posts.extend(posts)

    if SOURCES.get("mastodon", {}).get("enabled"):
        print("\n📥 Mastodon trending...")
        posts = mastodon.collect()
        print(f"  Итого: {len(posts)} постов")
        all_posts.extend(posts)

    if SOURCES.get("stackoverflow", {}).get("enabled"):
        print("\n📥 Stack Overflow hot...")
        posts = stackoverflow.collect()
        print(f"  Итого: {len(posts)} постов")
        all_posts.extend(posts)

    return all_posts


def deduplicate(posts: list) -> list:
    seen: set[str] = set()
    unique = []
    for p in posts:
        if p.url not in seen:
            seen.add(p.url)
            unique.append(p)
    return unique


def sort_by_engagement(posts: list) -> list:
    return sorted(posts, key=lambda p: p.score + p.comments * 2, reverse=True)


def collect_news() -> list:
    all_items = []

    print("\n📡 RSS feeds...")
    all_items.extend(rss_news.collect())

    print("\n📰 The Guardian...")
    all_items.extend(guardian_news.collect())

    seen: set[str] = set()
    unique = []
    for item in all_items:
        if item.url not in seen:
            seen.add(item.url)
            unique.append(item)
    return unique


def run_tech(vault_path: str):
    print(f"\n{'='*50}")
    print(f"🚀 Tech Pipeline — {date.today()}")
    print(f"{'='*50}")

    try:
        all_posts = collect_tech()
        all_posts = deduplicate(all_posts)
        all_posts = sort_by_engagement(all_posts)
        print(f"\n✅ Всего уникальных постов: {len(all_posts)}")

        if not all_posts:
            print("❌ Нет постов для анализа.")
            return None

        print("\n🧠 Анализ через Gemini API...")
        result = analyze_tech(all_posts)
        result["total_posts_analyzed"] = len(all_posts)

        print(f"\n💾 Сохранение...")
        filepath = save_tech(result, all_posts, vault_path)
        print(f"✅ Файл создан: {filepath}")

        clusters = result.get("clusters", [])
        print(f"\n📊 Топ-3 темы дня:")
        for c in clusters[:3]:
            print(f"  {c['rank']}. {c['topic']} (engagement: {c.get('total_engagement', 0):,})")

        return result

    except Exception as e:
        print(f"❌ Tech pipeline failed: {e}")
        return None


def run_news(vault_path: str, rates_delta=None):
    print(f"\n{'='*50}")
    print(f"🌍 News Pipeline — {date.today()}")
    print(f"{'='*50}")

    try:
        all_items = collect_news()
        print(f"\n✅ Всего уникальных новостей: {len(all_items)}")

        if not all_items:
            print("❌ Нет новостей для анализа.")
            return None

        print("\n🧠 Анализ через Gemini API...")
        result = analyze_news(all_items)

        print(f"\n💾 Сохранение...")
        filepath = save_news(result, all_items, vault_path, rates_delta=rates_delta)
        print(f"✅ Файл создан: {filepath}")

        clusters = result.get("clusters", [])
        print(f"\n📊 Топ-3 новости дня:")
        for c in clusters[:3]:
            print(f"  {c['rank']}. {c['topic']} (significance: {c.get('significance', '?')}/10)")

        return result

    except Exception as e:
        print(f"❌ News pipeline failed: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Daily digest aggregator")
    parser.add_argument(
        "--mode",
        choices=["tech", "news", "all"],
        default="all",
        help="Which pipeline to run (default: all)",
    )
    args = parser.parse_args()

    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH", "./output/vault")

    # Fetch currency rates before news pipeline (github mode only)
    rates_delta = None
    if config.OUTPUT_MODE == "github" and args.mode in ("news", "all"):
        try:
            from collectors.currency import fetch_and_save_rates, get_rates_with_delta
            print("\n💱 Загрузка курсов валют...")
            fetch_and_save_rates()
            rates_delta = get_rates_with_delta()
            print(f"✅ Курсы загружены")
        except Exception as e:
            print(f"⚠️  Курсы валют недоступны: {e}")

    if args.mode in ("tech", "all"):
        run_tech(vault_path)

    if args.mode in ("news", "all"):
        run_news(vault_path, rates_delta=rates_delta)


if __name__ == "__main__":
    main()
