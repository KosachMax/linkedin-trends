from trends.ai.schemas import EventSynthesis
from trends.domain.models import Article


def validate_synthesis(event: EventSynthesis, articles: list[Article], minimum_sources: int) -> list[str]:
    by_id = {article.id: article for article in articles}
    errors: list[str] = []
    referenced = set(event.article_ids)
    unknown = referenced - by_id.keys()
    if unknown:
        errors.append(f"unknown article ids: {sorted(unknown)}")
    source_count = len({by_id[item].source_id for item in referenced if item in by_id})
    if source_count < minimum_sources:
        errors.append(f"requires {minimum_sources} independent sources, got {source_count}")
    for index, fact in enumerate(event.facts):
        fact_unknown = set(fact.article_ids) - by_id.keys()
        if fact_unknown:
            errors.append(f"fact {index} references unknown articles: {sorted(fact_unknown)}")
    return errors

