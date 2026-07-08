"""
Obsidian writer — генерирует .md файл в Obsidian/Quartz формате.
"""
from datetime import date
from pathlib import Path
import config


def render(data: dict, all_posts: list) -> str:
    today = date.today().strftime("%Y-%m-%d")
    total = data.get("total_posts_analyzed", len(all_posts))
    clusters = data.get("clusters", [])

    source_counts: dict[str, int] = {}
    for p in all_posts:
        key = p.source.split("/")[0]
        source_counts[key] = source_counts.get(key, 0) + 1

    sources_line = " · ".join(f"{k}: {v}" for k, v in sorted(source_counts.items()))

    lines = [
        "---",
        f'title: "Tech Trends — {today}"',
        f"date: {today}",
        "tags:",
        "  - tech",
        "  - trends",
        "---",
        "",
        f"> [!note] Дайджест дня",
        f"> Проанализировано **{total} постов** из {len(source_counts)} источников",
        f"> {sources_line}",
        "",
    ]

    top5 = sorted(all_posts, key=lambda p: p.score + p.comments * 2, reverse=True)[:5]
    if top5:
        lines.append("> [!important] 🔥 Топ-5 виральных постов")
        for i, p in enumerate(top5, 1):
            engagement = p.score + p.comments * 2
            lines.append(
                f"> {i}. [{p.title}]({p.url}) — `{p.source}` · "
                f"engagement {engagement:,} · ↑{p.score:,} · 💬 {p.comments:,}"
            )
        lines.append("")

    for c in clusters:
        rank = int(c.get("rank") or 0)
        topic = c.get("topic") or "—"
        desc = c.get("description") or ""
        hook = c.get("linkedin_hook") or ""
        engagement = int(c.get("total_engagement") or 0)
        post_count = int(c.get("post_count") or 0)
        tags = " ".join(c.get("tags") or [])
        top_posts = c.get("top_posts") or []

        callout = "[!danger]" if rank <= 3 else "[!tip]"

        lines += [
            f"> {callout} #{rank} {topic}",
            f"> **Engagement:** {engagement:,}  |  **Постов:** {post_count}",
            ">",
            f"> {desc}",
            ">",
            f"> **📌 LinkedIn hook:**",
            f"> {hook}",
        ]

        if top_posts:
            lines.append(">")
            lines.append("> **Топ материалы:**")
            for p in top_posts[:5]:
                t = p.get("title") or "—"
                u = p.get("url") or ""
                s = p.get("source") or ""
                sc = int(p.get("score") or 0)
                lines.append(f"> - [{t}]({u}) `{s}` ↑{sc}")

        if tags:
            lines.append(">")
            lines.append(f"> {tags}")

        lines.append("")

    lines += [f"> [!success] Источники"]
    for k, v in sorted(source_counts.items()):
        lines.append(f"> - **{k}**: {v} постов")

    lines += ["", f"*Сгенерировано автоматически · {today}*"]

    return "\n".join(lines)


def save(data: dict, all_posts: list, vault_path: str) -> Path:
    today = date.today().strftime("%Y-%m-%d")
    md_content = render(data, all_posts)

    if config.OUTPUT_MODE == "github":
        output_dir = Path(config.DOCS_PATH) / "tech"
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / f"{today}.md"
        md_path.write_text(md_content, encoding="utf-8")

        from output.index_writer import generate_index
        generate_index(config.DOCS_PATH, tech_data=data)

        return md_path
    else:
        output_dir = Path(vault_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / f"{today}-linkedin-trends.md"
        filepath.write_text(md_content, encoding="utf-8")
        return filepath
