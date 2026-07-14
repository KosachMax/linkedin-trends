import re

from trends.ai.schemas import EventSynthesis
from trends.domain.models import Article


def is_russian_editorial(value: str) -> bool:
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", value))
    latin = len(re.findall(r"[A-Za-z]", value))
    if cyrillic < 2:
        return False
    # Product names, model identifiers and organisations can legitimately make
    # technical copy Latin-heavy. A complete English sentence still fails
    # because it contains no meaningful Cyrillic editorial text.
    return latin <= max(48, int(cyrillic * 0.9))


def validate_synthesis(event: EventSynthesis, articles: list[Article], minimum_sources: int) -> list[str]:
    by_id = {article.id: article for article in articles}
    errors: list[str] = []
    referenced_list = event.article_ids
    referenced = set(referenced_list)
    if len(referenced_list) != len(referenced):
        errors.append("event article_ids must not contain duplicates")
    unknown = referenced - by_id.keys()
    if unknown:
        errors.append(f"unknown article ids: {sorted(unknown)}")
    missing = by_id.keys() - referenced
    if missing:
        errors.append(f"event must include every input article id: {sorted(missing)}")
    source_count = len({by_id[item].source_id for item in referenced if item in by_id})
    if source_count < minimum_sources:
        errors.append(f"requires {minimum_sources} independent sources, got {source_count}")
    if not 200 <= len(event.brief) <= 800:
        errors.append(
            f"brief must contain 200-800 characters, got {len(event.brief)}"
        )
    for index, fact in enumerate(event.facts):
        fact_unknown = set(fact.article_ids) - referenced
        if fact_unknown:
            errors.append(
                f"fact {index} references articles outside the event: "
                f"{sorted(fact_unknown)}"
            )
    russian_fields = {
        "title": event.title,
        "brief": event.brief,
        "context": event.context,
        "why_it_matters": event.why_it_matters,
        "category": event.category,
    }
    for field, value in russian_fields.items():
        if not is_russian_editorial(value):
            errors.append(f"{field} must be predominantly written in Russian")
    for index, fact in enumerate(event.facts):
        if not is_russian_editorial(fact.text):
            errors.append(f"fact {index} must be predominantly written in Russian")
    return errors
