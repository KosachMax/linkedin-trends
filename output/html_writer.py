"""
HTML writer — утилиты для github mode:
- конвертация Obsidian callouts → MkDocs admonitions
- генерация docs/index.md
"""
import re
from datetime import date
from pathlib import Path

CALLOUT_TO_ADMONITION = {
    "note":    "note",
    "idea":    "tip",
    "danger":  "danger",
    "warning": "warning",
    "done":    "success",
}


def obsidian_to_mkdocs(text: str) -> str:
    """Convert Obsidian callout syntax to MkDocs admonition syntax."""
    lines = text.split("\n")
    output = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^> \[!(\w+)\](.*)", line)
        if m:
            ctype = m.group(1).lower()
            title = m.group(2).strip()
            mktype = CALLOUT_TO_ADMONITION.get(ctype, ctype)
            header = f'!!! {mktype}' + (f' "{title}"' if title else '')
            output.append(header)
            i += 1
            while i < len(lines) and (lines[i].startswith("> ") or lines[i] == ">"):
                content = lines[i][2:] if lines[i].startswith("> ") else ""
                output.append(f"    {content}")
                i += 1
        else:
            output.append(line)
            i += 1
    return "\n".join(output)


def obsidian_links_to_md(text: str) -> str:
    """Convert [[#Heading]] to [Heading](#heading)."""
    def to_anchor(m):
        heading = m.group(1)
        slug = heading.lower().replace(" ", "-")
        return f"[{heading}](#{slug})"
    return re.sub(r"\[\[#([^\]]+)\]\]", to_anchor, text)


def prepare_for_mkdocs(text: str) -> str:
    text = obsidian_links_to_md(text)
    text = obsidian_to_mkdocs(text)
    return text


def write_index(docs_path: str) -> Path:
    docs = Path(docs_path)
    tech_files = sorted((docs / "tech").glob("*.md"), reverse=True)
    news_files = sorted((docs / "news").glob("*.md"), reverse=True)
    today = date.today().strftime("%Y-%m-%d")

    def date_list(files, subdir):
        if not files:
            return "_Нет отчётов_"
        rows = ["| Дата | |", "|---|---|"]
        for f in files[:30]:
            stem = f.stem
            badge = " 🆕" if stem == today else ""
            rows.append(f"| {stem}{badge} | [Открыть →]({subdir}/{stem}.md) |")
        return "\n".join(rows)

    content = f"""# 📊 Daily Trends

Автоматический дайджест — tech тренды и мировые новости.
Обновляется ежедневно в **09:00 МСК**.

## 🚀 Tech Trends

{date_list(tech_files, "tech")}

## 🌍 World News

{date_list(news_files, "news")}

---
*Последнее обновление: {today}*
"""
    index_path = docs / "index.md"
    index_path.write_text(content, encoding="utf-8")
    return index_path
