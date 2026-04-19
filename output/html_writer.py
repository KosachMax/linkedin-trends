"""
Index writer — генерирует quartz/content/index.md с wikilinks.
"""
from datetime import date
from pathlib import Path


def write_index(docs_path: str) -> Path:
    content_dir = Path(docs_path)
    tech_files = sorted((content_dir / "tech").glob("*.md"), reverse=True)
    news_files = sorted((content_dir / "news").glob("*.md"), reverse=True)
    today = date.today().strftime("%Y-%m-%d")

    def wikilink_list(files, subdir):
        if not files:
            return "_Нет отчётов_"
        rows = []
        for f in files[:30]:
            stem = f.stem
            try:
                d = date.fromisoformat(stem)
                label = f"{d.strftime('%B')} {d.day}, {d.year}"
            except ValueError:
                label = stem
            rows.append(f"- [[{subdir}/{stem}|{label}]]")
        return "\n".join(rows)

    latest_tech = tech_files[0].stem if tech_files else None
    latest_news = news_files[0].stem if news_files else None

    tech_callout = ""
    if latest_tech:
        tech_callout = f"\n> [!tip] Latest\n> [[tech/{latest_tech}|Today's Tech Trends]]\n"

    news_callout = ""
    if latest_news:
        news_callout = f"\n> [!tip] Latest\n> [[news/{latest_news}|Today's World News]]\n"

    content = f"""---
title: Daily Trends
---

# 📊 Daily Trends

Автоматический дайджест — tech тренды и мировые новости.
Обновляется ежедневно в **09:00 МСК**.

## 🚀 Tech Trends
{tech_callout}
{wikilink_list(tech_files, "tech")}

## 🌍 World News
{news_callout}
{wikilink_list(news_files, "news")}

---
*Последнее обновление: {today}*
"""
    index_path = content_dir / "index.md"
    index_path.write_text(content, encoding="utf-8")
    return index_path
