"""
News Analyzer — отправляет новости в Google Gemini API и получает кластеры тем.
"""
import json
import os
import re
import time

from openai import OpenAI
from config import NEWS_TOP_COUNT, NEWS_MAX_FOR_ANALYSIS

MODEL = "gemini-2.5-flash-lite"


def build_prompt(items: list) -> str:
    lines = []
    for i, item in enumerate(items[:NEWS_MAX_FOR_ANALYSIS], 1):
        lang_note = f" [lang:{item.language}]" if hasattr(item, "language") and item.language != "en" else ""
        lines.append(
            f"{i}. [{item.source}]{lang_note} {item.title}"
            + (f"\n   URL: {item.url}" if item.url else "")
            + (f"\n   {item.summary[:300]}" if item.summary else "")
        )

    news_block = "\n".join(lines)

    return f"""Ты — аналитик мировых новостей. Тебе дан список свежих новостей из 12+ ведущих мировых СМИ.

Твоя задача — кластеризировать новости по темам и выдать топ-{NEWS_TOP_COUNT} наиболее значимых историй по темам: политика, войны/конфликты, экономика, мировые события.

НОВОСТИ:
{news_block}

ИНСТРУКЦИИ:
1. Сгруппируй новости по смысловым темам (политика, конфликты, экономика, дипломатия и т.д.)
2. Оцени значимость каждой темы по шкале 1-10 (10 = глобальное влияние)
3. Отсортируй темы по значимости (от большей к меньшей)
4. Для каждой темы укажи затронутые географии и ключевые фигуры
5. Новости могут быть на английском, французском, немецком, русском языках.
   Переведи заголовки и резюме на русский язык в своём ответе вне зависимости от языка источника.
6. Посты приходят из 12+ источников. Убедись, что итоговые кластеры отражают
   географическое и тематическое разнообразие — не акцентируй внимание на одном регионе
   или источнике. Каждый кластер должен ссылаться минимум на 2 разных источника.
7. В top_articles ОБЯЗАТЕЛЬНО сохраняй оригинальные URL статей точно как они переданы.
   Добавь поле "source_domain" для каждой статьи (например: "reuters.com", "bbc.com").

Отвечай ТОЛЬКО в формате JSON, без markdown-блоков, без пояснений:
{{
  "date": "YYYY-MM-DD",
  "total_analyzed": <int>,
  "clusters": [
    {{
      "rank": 1,
      "topic": "Название темы (кратко, 3-6 слов, на русском)",
      "significance": <int 1-10>,
      "summary": "Суть события — 3-4 предложения на русском о том, что происходит и почему это важно",
      "geographies": ["Страна1", "Страна2"],
      "key_figures": ["Имя1", "Имя2"],
      "top_articles": [
        {{"title": "Заголовок на русском", "url": "https://...", "source": "Reuters", "source_domain": "reuters.com"}},
        {{"title": "Заголовок на русском", "url": "https://...", "source": "BBC", "source_domain": "bbc.com"}}
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

    last_err = None
    for attempt in range(3):
        try:
            message = client.chat.completions.create(
                model=MODEL,
                max_tokens=8192,
                messages=[{"role": "user", "content": build_prompt(items)}],
            )
            break
        except Exception as e:
            last_err = e
            print(f"  [news-llm] attempt {attempt + 1} failed: {e}")
            time.sleep(5 * (attempt + 1))
    else:
        raise last_err

    raw = (message.choices[0].message.content or "").strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    raw = re.sub(r"^\s*//.*$", "", raw, flags=re.MULTILINE)
    raw = re.sub(r",(\s*[\]\}])", r"\1", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [news-llm] JSON parse error at line {e.lineno} col {e.colno}: {e.msg}")
        print(f"  [news-llm] raw response head: {raw[:500]}")
        print(f"  [news-llm] raw response tail: {raw[-500:]}")
        raise
