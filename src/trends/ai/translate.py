"""
Google Cloud Translation API v2 (Basic) client.

Uses the same GOOGLE_API_KEY as Gemini. Requires the Cloud Translation API
to be enabled on the same Google Cloud project:
https://console.cloud.google.com/apis/library/translate.googleapis.com

If the API is not enabled or the call fails, the original text is returned
unchanged — translation is best-effort and never blocks synthesis.
"""
from __future__ import annotations

import re
import sys

import httpx

_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2"
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
_MIN_CYRILLIC_RATIO = 0.15  # text is "Russian enough" if ≥15% chars are Cyrillic


def _needs_translation(text: str) -> bool:
    if not text:
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    cyrillic = sum(1 for c in letters if _CYRILLIC.match(c))
    return cyrillic / len(letters) < _MIN_CYRILLIC_RATIO


async def translate_to_russian(texts: list[str], api_key: str) -> list[str]:
    """Translate a batch of texts to Russian. Returns originals on any error."""
    indices = [i for i, t in enumerate(texts) if _needs_translation(t)]
    if not indices:
        return texts

    batch = [texts[i] for i in indices]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                _TRANSLATE_URL,
                params={"key": api_key},
                json={"q": batch, "target": "ru", "format": "text"},
            )
            response.raise_for_status()
            translated = [item["translatedText"] for item in response.json()["data"]["translations"]]
    except Exception as exc:
        print(f"[translate] failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return texts

    result = list(texts)
    for idx, translation in zip(indices, translated):
        result[idx] = translation
    return result
