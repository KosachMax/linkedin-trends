"""
News writer — генерирует world-news .md (и .html в github mode).
"""
import requests
from datetime import date
from pathlib import Path
import config
from output.html_writer import md_to_html

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


def fetch_rates() -> dict[str, str]:
    headers = {"User-Agent": "Mozilla/5.0"}
    rates = {}
    for code, pair in [("USD", "USDRUB=X"), ("EUR", "EURRUB=X")]:
        try:
            resp = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{pair}?interval=1d&range=1d",
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            price = resp.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
            rates[code] = f"{price:.2f}"
        except Exception as e:
            print(f"  [yahoo] Ошибка курса {code}: {e}")
    return rates


def geo_with_flag(geo: str) -> str:
    return f"{GEO_FLAGS.get(geo, '🌐')} {geo}"


def render(data: dict, item_count: int) -> str:
    today = date.today().strftime("%Y-%m-%d")
    clusters = data.get("clusters", [])

    all_figures: dict[str, int] = {}
    for c in clusters:
        for f in c.get("key_figures", []):
            all_figures[f] = all_figures.get(f, 0) + 1

    rates = fetch_rates()
    usd = rates.get("USD", "н/д")
    eur = rates.get("EUR", "н/д")

    lines = [
        f"# 🌍 World News — {today}",
        "",
        f"> [!note] Дайджест мировых новостей",
        f"> Проанализировано **{item_count} новостей** из международных источников",
        f"> Кластеров тем: **{len(clusters)}**",
        f">",
        f"> 💵 **USD/RUB:** {usd} ₽  ·  💶 **EUR/RUB:** {eur} ₽  _(Yahoo Finance)_",
        "",
        "## Содержание",
        "",
    ]

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

        lines += [
            f"## {topic}",
            "",
            f"> {callout} #{rank} Significance: {sig}/10",
            f"> {summary}",
        ]

        if geos or figures:
            lines.append(">")
            if geos:
                lines.append(f"> **Регионы:** {' · '.join(geos)}")
            if figures:
                lines.append(f"> **Фигуранты:** {', '.join(figures)}")

        if articles:
            lines.append(">")
            lines.append("> **Источники:**")
            for a in articles[:3]:
                title = a.get("title", "")
                url = a.get("url", "")
                source = a.get("source", "")
                lines.append(f"> - [{title}]({url}) `{source}`" if url else f"> - {title} `{source}`")

        if tags:
            lines += ["", tags]

        lines += ["", "---", ""]

    if all_figures:
        lines += ["## Ключевые фигуры", ""]
        for name, count in sorted(all_figures.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- **{name}** — упомянут в {count} {'теме' if count == 1 else 'темах'}")
        lines.append("")

    lines += ["#news #politics #economics #world", "", f"*Сгенерировано автоматически · {today}*"]

    return "\n".join(lines)


def save(data: dict, items: list, vault_path: str) -> Path:
    today = date.today().strftime("%Y-%m-%d")
    md_content = render(data, len(items))

    if config.OUTPUT_MODE == "github":
        output_dir = Path(config.DOCS_PATH) / "news"
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / f"{today}.md"
        md_path.write_text(md_content, encoding="utf-8")
        html_path = output_dir / f"{today}.html"
        html_path.write_text(
            md_to_html(md_content, f"World News {today}"),
            encoding="utf-8",
        )
        return html_path
    else:
        output_dir = Path(vault_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / f"{today}-world-news.md"
        filepath.write_text(md_content, encoding="utf-8")
        return filepath
