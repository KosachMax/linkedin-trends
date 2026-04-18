"""
Analyzer — отправляет посты в Google Gemini API и получает топ-10 кластеров тем.
"""
import json
import os
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

    return f"""Ты — аналитик контента для LinkedIn. Тебе дан список топовых постов из Reddit, Hacker News и Dev.to за сегодня по темам: Python, AI/ML, backend, software development.

Твоя задача — кластеризировать эти посты по смысловым темам и выдать топ-{CLUSTER_COUNT} тем, которые БОЛЬШЕ ВСЕГО резонируют с аудиторией технических специалистов.

ПОСТЫ:
{posts_block}

ИНСТРУКЦИИ:
1. Найди повторяющиеся смысловые паттерны и сгруппируй посты по темам
2. Для каждой темы посчитай суммарный engagement (score + comments*2)
3. Отсортируй темы по суммарному engagement (от большего к меньшему)
4. Для каждой темы придумай цепляющий заголовок для LinkedIn-поста

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
        {{"title": "...", "url": "...", "source": "...", "score": <int>}}
      ],
      "tags": ["#tag1", "#tag2", "#tag3"]
    }}
  ]
}}"""


def analyze(posts: list) -> dict:
    client = OpenAI(
        api_key=os.environ["GOOGLE_API_KEY"],
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    print(f"  [llm] Отправляю {min(len(posts), MAX_POSTS_FOR_ANALYSIS)} постов на анализ...")

    message = client.chat.completions.create(
        model=MODEL,
        max_tokens=8192,
        messages=[{"role": "user", "content": build_prompt(posts)}],
    )

    raw = message.choices[0].message.content.strip()

    # Очищаем на случай если модель всё же добавила ```json
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw)
