"""
News writer — генерирует world-news .md в Obsidian/Quartz формате.
"""
from datetime import date
from pathlib import Path
import config

GEO_FLAGS = {
    "USA": "🇺🇸", "US": "🇺🇸", "United States": "🇺🇸", "America": "🇺🇸",
    "Russia": "🇷🇺", "РФ": "🇷🇺",
    "Ukraine": "🇺🇦", "Украина": "🇺🇦",
    "China": "🇨🇳", "Китай": "🇨🇳",
    "UK": "🇬🇧", "Britain": "🇬🇧", "England": "🇬🇧",
    "Germany": "🇩🇪", "Германия": "🇩🇪",
    "France": "🇫🇷", "Франция": "🇫🇷",
    "Israel": "🇮🇱", "Израиль": "🇮🇱",
    "Iran": "🇮🇷", "Иран": "🇮🇷",
    "Gaza": "🇵🇸", "Palestine": "🇵🇸",
    "Turkey": "🇹🇷", "Турция": "🇹🇷",
    "India": "🇮🇳", "Индия": "🇮🇳",
    "Japan": "🇯🇵", "Япония": "🇯🇵",
    "Europe": "🇪🇺", "EU": "🇪🇺", "Европа": "🇪🇺",
    "Middle East": "🌍", "Africa": "🌍", "Asia": "🌏",
}


def geo_with_flag(geo: str) -> str:
    return f"{GEO_FLAGS.get(geo, '🌐')} {geo}"


def _render_currency_block(rates_delta: dict, today: str) -> list[str]:
    if not rates_delta:
        return []

    parts = []
    for key in ["USDRUB", "EURRUB", "CNYRUB"]:
        r = rates_delta.get(key)
        if not r or r.get("rate") is None:
            continue
        label = r["label"]
        rate = r["rate"]
        suffix = r["suffix"]
        arrow = r.get("arrow", "—")
        delta_str = r.get("delta_str", "—")
        pct = r.get("pct", "—")
        if arrow != "—" and delta_str != "—":
            parts.append(f"{label}: {rate:.2f} {suffix} {arrow} {delta_str} ({pct})")
        else:
            parts.append(f"{label}: {rate:.2f} {suffix}")

    if not parts:
        return []
    return [f"💱 {' · '.join(parts)}", ""]


def render(data: dict, item_count: int, rates_delta=None) -> str:
    today = date.today().strftime("%Y-%m-%d")
    clusters = data.get("clusters", [])

    all_figures: dict[str, int] = {}
    for c in clusters:
        for f in c.get("key_figures", []):
            all_figures[f] = all_figures.get(f, 0) + 1

    lines = [
        "---",
        f'title: "World News — {today}"',
        f"date: {today}",
        "tags:",
        "  - news",
        "  - politics",
        "  - economics",
        "---",
        "",
        f"> [!note] Дайджест мировых новостей",
        f"> Проанализировано **{item_count} новостей** из международных источников",
        f"> Кластеров тем: **{len(clusters)}**",
        "",
    ]

    # Enhanced currency block
    currency_lines = _render_currency_block(rates_delta or {}, today)
    if currency_lines:
        lines += currency_lines + [""]

    lines += ["## Содержание", ""]

    for c in clusters:
        sig = c["significance"]
        marker = "🔴" if sig >= 8 else "🟡" if sig >= 5 else "🟢"
        lines.append(f"- {marker} [[#{c['topic']}]] — significance {sig}/10")

    lines += ["", "---", ""]

    for c in clusters:
        rank = c["rank"]
        topic = c["topic"]
        sig = c["significance"]
        summary = c["summary"]
        geos = [geo_with_flag(g) for g in c.get("geographies", [])]
        figures = c.get("key_figures", [])
        articles = c.get("top_articles", [])
        tags = " ".join(c.get("tags", []))

        callout = "[!danger]" if sig >= 8 else "[!warning]" if sig >= 5 else "[!note]"

        meta_parts = [f"#{rank} · {sig}/10"]
        if geos:
            meta_parts.append(" · ".join(geos))
        if figures:
            meta_parts.append(", ".join(figures))
        meta_line = " · ".join(meta_parts)

        lines += [
            f"## {topic}",
            "",
            f"> {callout} {meta_line}",
            "",
            summary,
            "",
        ]

        # Source links OUTSIDE callout (improvement 2)
        if articles:
            lines.append("**Источники:**")
            for a in articles[:3]:
                title = a.get("title", "")
                url = a.get("url", "")
                domain = a.get("source_domain", "") or a.get("source", "")
                if url:
                    lines.append(f"- [{title}]({url}) — `{domain}`")
                else:
                    lines.append(f"- {title} — `{domain}`")
            lines.append("")

        if tags:
            lines += [tags, ""]

        lines += ["---", ""]

    if all_figures:
        lines += ["## Ключевые фигуры", ""]
        for name, count in sorted(all_figures.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- **{name}** — упомянут в {count} {'теме' if count == 1 else 'темах'}")
        lines.append("")

    lines += ["#news #politics #economics #world", "", f"*Сгенерировано автоматически · {today}*"]

    return "\n".join(lines)


def save(data: dict, items: list, vault_path: str, rates_delta=None) -> Path:
    today = date.today().strftime("%Y-%m-%d")
    md_content = render(data, len(items), rates_delta=rates_delta)

    if config.OUTPUT_MODE == "github":
        output_dir = Path(config.DOCS_PATH) / "news"
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / f"{today}.md"
        md_path.write_text(md_content, encoding="utf-8")

        from output.index_writer import generate_index
        generate_index(config.DOCS_PATH, news_data=data)

        return md_path
    else:
        output_dir = Path(vault_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / f"{today}-world-news.md"
        filepath.write_text(md_content, encoding="utf-8")
        return filepath
