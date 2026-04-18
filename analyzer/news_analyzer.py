"""
News Analyzer — отправляет новости в Google Gemini API и получает кластеры тем.
"""
import json
import os
from openai import OpenAI
from config import NEWS_TOP_COUNT, NEWS_MAX_FOR_ANALYSIS

MODEL = "gemini-2.5-flash-lite"


def build_prompt(items: list) -> str:
    lines = []
    for i, item in enumerate(items[:NEWS_MAX_FOR_ANALYSIS], 1):
        lines.append(
            f"{i}. [{item.source}] {item.title}"
            + (f"\n   {item.summary[:300]}" if item.summary else "")
        )

    news_block = "\n".join(lines)

    return f"""Ты — аналитик мировых новостей. Тебе дан список свежих новостей из ведущих мировых СМИ.

Твоя задача — кластеризировать новости по темам и выдать топ-{NEWS_TOP_COUNT} наиболее значимых историй по темам: политика, войны/конфликты, экономика, мировые события.

НОВОСТИ:
{news_block}

ИНСТРУКЦИИ:
1. Сгруппируй новости по смысловым темам (политика, конфликты, экономика, дипломатия и т.д.)
2. Оцени значимость каждой темы по шкале 1-10 (10 = глобальное влияние)
3. Отсортируй темы по значимости (от большей к меньшей)
4. Для каждой темы укажи затронутые географии и ключевые фигуры

Отвечай ТОЛЬКО в формате JSON, без markdown-блоков, без пояснений:
{{
  "date": "YYYY-MM-DD",
  "total_analyzed": <int>,
  "clusters": [
    {{
      "rank": 1,
      "topic": "Название темы (кратко, 3-6 слов)",
      "significance": <int 1-10>,
      "summary": "Суть события — 3-4 предложения о том, что происходит и почему это важно",
      "geographies": ["Страна1", "Страна2"],
      "key_figures": ["Имя1", "Имя2"],
      "top_articles": [
        {{"title": "...", "url": "...", "source": "..."}},
        {{"title": "...", "url": "...", "source": "..."}}
      ],
      "tags": ["#politics", "#economics"]
    }}
  ]
}}"""


def analyze(items: list) -> dict:
    client = OpenAI(
        api_key=os.environ["GOOGLE_API_KEY"],
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    print(f"  [news-llm] Отправляю {min(len(items), NEWS_MAX_FOR_ANALYSIS)} новостей на анализ...")

    message = client.chat.completions.create(
        model=MODEL,
        max_tokens=8192,
        messages=[{"role": "user", "content": build_prompt(items)}],
    )

    raw = message.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw)
