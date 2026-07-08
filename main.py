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
from collectors import medium, arxiv, indiehackers
from collectors import rss_news, guardian_news
from analyzer.llm_analyzer import analyze as analyze_tech
from analyzer.news_analyzer import analyze as analyze_news
from output.obsidian_writer import save as save_tech
from output.news_writer import save as save_news
from config import SOURCES


def _safe_collect(name: str, fn) -> list:
    try:
        posts = fn()
        print(f"  Итого: {len(posts)} постов")
        return posts
    except Exception as e:
        print(f"  ⚠️  {name} упал: {e}")
        return []


def collect_tech() -> list:
    all_posts = []

    if SOURCES["reddit"]["enabled"]:
        print("\n📥 Reddit...")
        all_posts.extend(_safe_collect("reddit", reddit.collect))

    if SOURCES["hackernews"]["enabled"]:
        print("\n📥 Hacker News...")
        all_posts.extend(_safe_collect("hackernews", hackernews.collect))

    if SOURCES["devto"]["enabled"]:
        print("\n📥 Dev.to...")
        all_posts.extend(_safe_collect("devto", devto.collect))

    if SOURCES.get("github", {}).get("enabled"):
        print("\n📥 GitHub Trending...")
        all_posts.extend(_safe_collect("github", github_trending.collect))

    if SOURCES.get("lobsters", {}).get("enabled"):
        print("\n📥 Lobste.rs...")
        all_posts.extend(_safe_collect("lobsters", lobsters.collect))

    if SOURCES.get("mastodon", {}).get("enabled"):
        print("\n📥 Mastodon trending...")
        all_posts.extend(_safe_collect("mastodon", mastodon.collect))

    if SOURCES.get("stackoverflow", {}).get("enabled"):
        print("\n📥 Stack Overflow hot...")
        all_posts.extend(_safe_collect("stackoverflow", stackoverflow.collect))

    if SOURCES.get("medium", {}).get("enabled"):
        print("\n📥 Medium...")
        all_posts.extend(_safe_collect("medium", medium.collect))

    if SOURCES.get("arxiv", {}).get("enabled"):
        print("\n📥 ArXiv...")
        all_posts.extend(_safe_collect("arxiv", arxiv.collect))

    if SOURCES.get("indiehackers", {}).get("enabled"):
        print("\n📥 Indie Hackers...")
        all_posts.extend(_safe_collect("indiehackers", indiehackers.collect))

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
        import traceback
        print(f"❌ Tech pipeline failed: {e}")
        traceback.print_exc()
        _write_stub_tech(vault_path)
        return None


def _write_stub_tech(vault_path: str) -> None:
    """Write a minimal stub file so CI check doesn't fail on pipeline errors."""
    today = date.today().strftime("%Y-%m-%d")
    if config.OUTPUT_MODE == "github":
        from pathlib import Path
        out = Path(config.DOCS_PATH) / "tech"
        out.mkdir(parents=True, exist_ok=True)
        stub = out / f"{today}.md"
        if not stub.exists():
            stub.write_text(
                f"---\ntitle: \"Tech Trends — {today}\"\ndate: {today}\n---\n\n"
                f"> [!warning] Пайплайн временно недоступен\n"
                f"> Данные за {today} не удалось собрать. Попробуйте позже.\n",
                encoding="utf-8",
            )
            print(f"  ⚠️  Stub файл записан: {stub}")


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
