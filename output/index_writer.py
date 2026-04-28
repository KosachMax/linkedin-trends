"""
Index writer — генерирует quartz/content/index.md и archive.md.
"""
import json
from datetime import date
from pathlib import Path

_DATA_DIR = Path("data")
_TECH_CACHE = _DATA_DIR / "tech_latest.json"
_NEWS_CACHE = _DATA_DIR / "news_latest.json"

PLATFORM_ICON = {
    "reddit":        "🟠 Reddit",
    "hackernews":    "🟡 HN",
    "dev.to":        "🟣 Dev.to",
    "github":        "⚫ GitHub",
    "lobsters":      "🔴 Lobsters",
    "mastodon":      "🐘 Mastodon",
    "stackoverflow": "🔵 SO",
}


def generate_index(docs_path: str, tech_data: dict = None, news_data: dict = None) -> None:
    content_dir = Path(docs_path)
    today = date.today().strftime("%Y-%m-%d")

    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    if tech_data is not None:
        _TECH_CACHE.write_text(
            json.dumps({"clusters": tech_data.get("clusters", [])[:3]}, ensure_ascii=False),
            encoding="utf-8",
        )
    if news_data is not None:
        _NEWS_CACHE.write_text(
            json.dumps({"clusters": news_data.get("clusters", [])[:3]}, ensure_ascii=False),
            encoding="utf-8",
        )

    tech_cache = _load_json(_TECH_CACHE) if tech_data is None else {"clusters": tech_data.get("clusters", [])[:3]}
    news_cache = _load_json(_NEWS_CACHE) if news_data is None else {"clusters": news_data.get("clusters", [])[:3]}

    tech_dates = {f.stem for f in (content_dir / "tech").glob("*.md")}
    news_dates = {f.stem for f in (content_dir / "news").glob("*.md")}
    all_dates = sorted(tech_dates | news_dates, reverse=True)

    tech_block = _build_tech_callout(tech_cache, today)
    news_block = _build_news_callout(news_cache, today)
    currency_block = _build_currency_callout()
    archive_rows = _build_archive_rows(all_dates[:30], tech_dates, news_dates)
    all_rows = _build_archive_rows(all_dates, tech_dates, news_dates)

    currency_section = f"\n{currency_block}\n" if currency_block else ""

    index_content = f"""---
title: Daily Trends
---
{currency_section}
{tech_block}

{news_block}

---

## 📁 Архив

| Дата | Tech Trends | World News |
|------|-------------|------------|
{archive_rows}

[[archive|Все отчёты →]]

---
*Обновляется ежедневно в 09:00 МСК*
"""
    (content_dir / "index.md").write_text(index_content, encoding="utf-8")

    archive_content = f"""---
title: Архив отчётов
---

# 📁 Архив отчётов

| Дата | Tech Trends | World News |
|------|-------------|------------|
{all_rows}

[[/|← Главная]]
"""
    (content_dir / "archive.md").write_text(archive_content, encoding="utf-8")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_tech_callout(data: dict, today: str) -> str:
    clusters = data.get("clusters", [])
    if not clusters:
        return f"> [!tip] 🚀 Tech Trends — {today}\n> *Данные обновляются...*\n> [[tech/{today}|Читать →]]"
    lines = [f"> [!tip] 🚀 Tech Trends — {today}", ">"]
    for c in clusters[:3]:
        eng = c.get("total_engagement", 0)
        platforms = _platforms_for_cluster(c.get("top_posts", []))
        suffix = (" · " + " · ".join(platforms)) if platforms else ""
        lines.append(f"> - **#{c['rank']} · {c['topic']}** — engagement {eng:,}{suffix}")
    lines += [">", f"> [[tech/{today}|Читать полный отчёт →]]"]
    return "\n".join(lines)


def _platforms_for_cluster(top_posts: list) -> list:
    """Top-1..2 платформ кластера. Вторую включаем только если её доля ≥ 30%."""
    if not top_posts:
        return []
    counts: dict[str, int] = {}
    for p in top_posts:
        src = (p.get("source") or "").split("/")[0].lower()
        if not src:
            continue
        counts[src] = counts.get(src, 0) + 1
    if not counts:
        return []
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(counts.values())
    result = []
    if ranked:
        result.append(PLATFORM_ICON.get(ranked[0][0], ranked[0][0]))
    if len(ranked) > 1 and ranked[1][1] / total >= 0.3:
        result.append(PLATFORM_ICON.get(ranked[1][0], ranked[1][0]))
    return result


def _build_news_callout(data: dict, today: str) -> str:
    clusters = data.get("clusters", [])
    if not clusters:
        return f"> [!danger] 🌍 World News — {today}\n> *Данные обновляются...*\n> [[news/{today}|Читать →]]"
    lines = [f"> [!danger] 🌍 World News — {today}", ">"]
    for c in clusters[:3]:
        sig = c.get("significance", 0)
        marker = "🔴" if sig >= 8 else "🟠" if sig >= 5 else "🟢"
        lines.append(f"> - {marker} **{c['topic']}** — {sig}/10")
    lines += [">", f"> [[news/{today}|Читать полный отчёт →]]"]
    return "\n".join(lines)


def _build_currency_callout() -> str:
    try:
        from collectors.currency import get_rates_with_delta
        rates = get_rates_with_delta()
        items = []
        for key in ["USDRUB", "EURRUB"]:
            r = rates.get(key)
            if not r or r.get("rate") is None:
                continue
            label = r["label"]
            rate = r["rate"]
            suffix = r["suffix"]
            arrow = r.get("arrow", "—")
            delta_str = r.get("delta_str", "—")
            pct = r.get("pct", "—")
            if arrow != "—" and delta_str != "—":
                items.append(f"> - **{label}:** {rate:.2f} {suffix} {arrow} {delta_str} ({pct})")
            else:
                items.append(f"> - **{label}:** {rate:.2f} {suffix}")
        if not items:
            return ""
        return "> [!info] 💱 Курсы валют\n" + "\n".join(items)
    except Exception:
        return ""


def _build_archive_rows(dates: list, tech_dates: set, news_dates: set) -> str:
    rows = []
    for d in dates:
        tech_link = f"[[tech/{d}|📊]]" if d in tech_dates else "—"
        news_link = f"[[news/{d}|🌍]]" if d in news_dates else "—"
        rows.append(f"| {d} | {tech_link} | {news_link} |")
    return "\n".join(rows) if rows else "| — | — | — |"
