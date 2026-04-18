"""
HTML writer — конвертирует .md в .html и генерирует index.html для GitHub Pages.
"""
import re
from datetime import date
from pathlib import Path

try:
    import markdown as md_lib
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

CALLOUT_STYLES = {
    "note":    ("#388bfd", "#0d2136"),
    "idea":    ("#c9a227", "#1c1700"),
    "danger":  ("#da3633", "#1e0d0d"),
    "warning": ("#d29922", "#1e1600"),
    "done":    ("#3fb950", "#0d1f0f"),
}

PAGE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
:root {{
  --bg: #0d1117; --bg2: #161b22; --border: #30363d;
  --text: #c9d1d9; --muted: #8b949e;
  --blue: #58a6ff; --purple: #d2a8ff; --green: #3fb950;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; line-height: 1.7; padding: 2rem 1rem; }}
.page {{ max-width: 860px; margin: 0 auto; }}
.back {{ margin-bottom: 1.5rem; }}
.back a {{ color: var(--muted); text-decoration: none; font-size: 0.9rem; }}
.back a:hover {{ color: var(--blue); }}
h1 {{ color: var(--blue); font-size: 1.8rem; border-bottom: 1px solid var(--border); padding-bottom: .6rem; margin-bottom: 1.5rem; }}
h2 {{ color: var(--purple); font-size: 1.3rem; margin: 2rem 0 .8rem; }}
h3 {{ color: #79c0ff; font-size: 1.1rem; margin: 1.5rem 0 .5rem; }}
a {{ color: var(--blue); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
p {{ margin: .6rem 0; }}
ul, ol {{ padding-left: 1.5rem; margin: .6rem 0; }}
li {{ margin: .25rem 0; }}
code {{ background: var(--bg2); padding: .15em .4em; border-radius: 4px; font-family: 'Fira Code', 'Cascadia Code', monospace; font-size: .88em; }}
pre {{ background: var(--bg2); padding: 1rem; border-radius: 6px; overflow-x: auto; margin: 1rem 0; }}
blockquote {{ border-left: 3px solid var(--border); padding: .4rem 1rem; margin: 1rem 0; background: var(--bg2); border-radius: 0 6px 6px 0; color: var(--muted); }}
hr {{ border: none; border-top: 1px solid var(--border); margin: 1.5rem 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border: 1px solid var(--border); padding: .4rem .8rem; text-align: left; }}
th {{ background: var(--bg2); color: #79c0ff; }}
strong {{ color: #e6edf3; }}
em {{ color: var(--muted); }}
.callout {{ padding: .9rem 1.1rem; margin: 1rem 0; border-radius: 0 8px 8px 0; }}
.callout p:first-child {{ margin-top: 0; }}
.callout p:last-child {{ margin-bottom: 0; }}
.meta {{ color: var(--muted); font-size: .85rem; margin-top: 3rem; border-top: 1px solid var(--border); padding-top: .8rem; }}
</style>
</head>
<body>
<div class="page">
<div class="back"><a href="{back}">&larr; Все отчёты</a></div>
{content}
<div class="meta">Сгенерировано автоматически &middot; {today}</div>
</div>
</body>
</html>
"""

INDEX_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Trends</title>
<style>
:root {{
  --bg: #0d1117; --bg2: #161b22; --border: #30363d;
  --text: #c9d1d9; --muted: #8b949e; --blue: #58a6ff;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; line-height: 1.6; padding: 2rem 1rem; }}
.page {{ max-width: 860px; margin: 0 auto; }}
h1 {{ color: var(--blue); font-size: 2rem; border-bottom: 1px solid var(--border); padding-bottom: .6rem; margin-bottom: .4rem; }}
.subtitle {{ color: var(--muted); font-size: .9rem; margin-bottom: 2.5rem; }}
.columns {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }}
@media (max-width: 600px) {{ .columns {{ grid-template-columns: 1fr; }} }}
.col h2 {{ font-size: 1.2rem; margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: .4rem; }}
.col h2.tech {{ color: #ff7b72; }}
.col h2.news {{ color: #3fb950; }}
.date-list {{ list-style: none; padding: 0; }}
.date-list li {{ display: flex; align-items: center; padding: .3rem 0; border-bottom: 1px solid var(--border); }}
.date-list li:last-child {{ border-bottom: none; }}
.date-list a {{ color: var(--blue); text-decoration: none; font-family: monospace; font-size: .95rem; flex: 1; }}
.date-list a:hover {{ text-decoration: underline; }}
.date-list .new {{ background: #388bfd22; color: var(--blue); font-size: .7rem; padding: .1rem .4rem; border-radius: 4px; margin-left: .5rem; border: 1px solid #388bfd44; }}
.empty {{ color: var(--muted); font-size: .9rem; }}
.footer {{ margin-top: 3rem; color: var(--muted); font-size: .8rem; border-top: 1px solid var(--border); padding-top: .8rem; }}
</style>
</head>
<body>
<div class="page">
<h1>📊 Daily Trends</h1>
<p class="subtitle">Автоматический дайджест — tech тренды и мировые новости</p>
<div class="columns">
  <div class="col">
    <h2 class="tech">🚀 Tech Trends</h2>
    {tech_list}
  </div>
  <div class="col">
    <h2 class="news">🌍 World News</h2>
    {news_list}
  </div>
</div>
<div class="footer">Обновляется ежедневно в 09:00 МСК &middot; {today}</div>
</div>
</body>
</html>
"""


def _preprocess_obsidian(text: str) -> str:
    """Convert Obsidian-specific syntax to standard markdown."""
    # [[#Heading]] → [Heading](#heading-slug)
    def obsidian_link(m):
        heading = m.group(1)
        slug = heading.lower().replace(" ", "-")
        return f"[{heading}](#{slug})"
    text = re.sub(r"\[\[#([^\]]+)\]\]", obsidian_link, text)
    return text


def _preprocess_callouts(text: str) -> str:
    """Convert Obsidian callout syntax to styled HTML divs."""
    lines = text.split("\n")
    output = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^> \[!(\w+)\](.*)", line)
        if m:
            ctype = m.group(1).lower()
            rest = m.group(2).strip()
            border, bg = CALLOUT_STYLES.get(ctype, ("#8b949e", "#161b22"))
            content_lines = []
            if rest:
                content_lines.append(rest)
            i += 1
            while i < len(lines) and (lines[i].startswith("> ") or lines[i] == ">"):
                content_lines.append(lines[i][2:] if lines[i].startswith("> ") else "")
                i += 1
            content_md = "\n".join(content_lines)
            output.append(
                f'<div class="callout callout-{ctype}" '
                f'style="border-left:4px solid {border};background:{bg}" '
                f'markdown="1">\n\n{content_md}\n\n</div>'
            )
        else:
            output.append(line)
            i += 1
    return "\n".join(output)


def md_to_html(md_content: str, title: str, back: str = "../../index.html") -> str:
    text = _preprocess_obsidian(md_content)
    text = _preprocess_callouts(text)

    if HAS_MARKDOWN:
        body = md_lib.markdown(
            text,
            extensions=["extra", "nl2br", "sane_lists"],
        )
    else:
        body = f"<pre>{text}</pre>"

    return PAGE_TEMPLATE.format(
        title=title,
        back=back,
        content=body,
        today=date.today().strftime("%Y-%m-%d"),
    )


def _build_date_list(html_files: list[Path], subdir: str) -> str:
    if not html_files:
        return '<p class="empty">Нет отчётов</p>'
    today_str = date.today().strftime("%Y-%m-%d")
    items = []
    for f in sorted(html_files, reverse=True)[:30]:
        stem = f.stem
        new_badge = ' <span class="new">new</span>' if stem == today_str else ""
        items.append(f'<li><a href="{subdir}/{f.name}">{stem}</a>{new_badge}</li>')
    return f'<ul class="date-list">{"".join(items)}</ul>'


def write_index(docs_path: str) -> Path:
    docs = Path(docs_path)
    tech_files = sorted((docs / "tech").glob("*.html"))
    news_files = sorted((docs / "news").glob("*.html"))

    html = INDEX_TEMPLATE.format(
        tech_list=_build_date_list(tech_files, "tech"),
        news_list=_build_date_list(news_files, "news"),
        today=date.today().strftime("%Y-%m-%d"),
    )
    index_path = docs / "index.html"
    index_path.write_text(html, encoding="utf-8")
    return index_path
