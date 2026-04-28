"""
Analyzer — отправляет посты в Google Gemini API и получает топ-10 кластеров тем.
"""
import json
import os
import re
import time

from openai import OpenAI
from config import CLUSTER_COUNT, MAX_POSTS_FOR_ANALYSIS

MODEL = "gemini-2.5-flash-lite"

def build_prompt(posts: list) -> str:
    lines = []
    for i, p in enumerate(posts[:MAX_POSTS_FOR_ANALYSIS], 1):
        engagement = p.score + p.comments * 2  # взвешенный engagement
        lines.append(
            f"{i}. [{p.source}] (engagement:{engagement}) {p.title}"
            + (f"\n   {p.text[:200]}" if p.text else "")
        )

    posts_block = "\n".join(lines)

    return f"""Ты — аналитик контента для LinkedIn. Тебе дан список топовых постов из Reddit, Hacker News, Dev.to, GitHub Trending, Lobste.rs, Mastodon и Stack Overflow за сегодня по темам: Python, AI/ML, backend, software development, open source.

Твоя задача — кластеризировать эти посты по смысловым темам и выдать топ-{CLUSTER_COUNT} тем, которые БОЛЬШЕ ВСЕГО резонируют с аудиторией технических специалистов.

ПОСТЫ:
{posts_block}

ИНСТРУКЦИИ:
1. Найди повторяющиеся смысловые паттерны и сгруппируй посты по темам.
2. Для каждой темы посчитай суммарный engagement (score + comments*2).
3. Отсортируй темы по суммарному engagement (от большего к меньшему).
4. Для каждой темы придумай цепляющий заголовок для LinkedIn-поста.
5. В `top_posts` каждой темы клади до 5 самых виральных постов этой темы (если в кластере меньше 5 постов — клади сколько есть).

КРИТИЧЕСКИ ВАЖНО:
- Верни РОВНО {CLUSTER_COUNT} кластеров — ни больше, ни меньше.
- Если близких тем не хватает — раскрывай разные грани одной (например: "AI/инфраструктура", "AI/безопасность", "AI/продуктовое применение", "Локальные LLM", "AI-tooling для разработчиков"). Темы должны быть различимы и не дублировать друг друга.
- В поле `source` каждого top_post клади ТОЧНО ту строку, что была в скобках `[...]` исходного поста (например: `reddit/r/Python`, `hackernews`, `dev.to/t/ai`, `github`, `lobsters`, `mastodon/hachyderm`, `stackoverflow`).

Отвечай ТОЛЬКО в формате JSON, без markdown-блоков, без пояснений:
{{
  "date": "YYYY-MM-DD",
  "total_posts_analyzed": <int>,
  "clusters": [
    {{
      "rank": 1,
      "topic": "Название темы (кратко, 3-6 слов)",
      "description": "Что именно обсуждают — 2-3 предложения о сути тренда",
      "linkedin_hook": "Цепляющий первый абзац для LinkedIn-поста на эту тему (2-3 предложения)",
      "total_engagement": <int>,
      "post_count": <int>,
      "top_posts": [
        {{"title": "...", "url": "...", "source": "...", "score": <int>}},
        {{"title": "...", "url": "...", "source": "...", "score": <int>}},
        {{"title": "...", "url": "...", "source": "...", "score": <int>}},
        {{"title": "...", "url": "...", "source": "...", "score": <int>}},
        {{"title": "...", "url": "...", "source": "...", "score": <int>}}
      ],
      "tags": ["#tag1", "#tag2", "#tag3"]
    }}
  ]
}}

Массив `clusters` должен содержать ровно {CLUSTER_COUNT} объектов такого вида."""


def analyze(posts: list) -> dict:
    client = OpenAI(
        api_key=os.environ["GOOGLE_API_KEY"],
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    print(f"  [llm] Отправляю {min(len(posts), MAX_POSTS_FOR_ANALYSIS)} постов на анализ...")

    last_err = None
    for attempt in range(3):
        try:
            message = client.chat.completions.create(
                model=MODEL,
                max_tokens=16384,
                messages=[{"role": "user", "content": build_prompt(posts)}],
            )
            break
        except Exception as e:
            last_err = e
            print(f"  [llm] attempt {attempt + 1} failed: {e}")
            time.sleep(5 * (attempt + 1))
    else:
        raise last_err

    raw = (message.choices[0].message.content or "").strip()

    # Очищаем на случай если модель всё же добавила ```json
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    # Удаляем JSON-несовместимые `// ...` комментарии (на случай если модель их вставила)
    raw = re.sub(r"^\s*//.*$", "", raw, flags=re.MULTILINE)
    # И trailing commas перед ]/}
    raw = re.sub(r",(\s*[\]\}])", r"\1", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [llm] JSON parse error at line {e.lineno} col {e.colno}: {e.msg}")
        print(f"  [llm] raw response head: {raw[:500]}")
        print(f"  [llm] raw response tail: {raw[-500:]}")
        print(f"  [llm] context around error: ...{raw[max(0, e.pos-100):e.pos+100]}...")
        raise
