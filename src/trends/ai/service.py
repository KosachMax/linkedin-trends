import json
import sys
from pathlib import Path

from trends.domain.models import Article

from .base import AIProvider
from .schemas import EventSynthesis
from .validate import validate_synthesis


class InvalidSynthesisError(ValueError):
    pass


class EventSynthesisService:
    def __init__(self, provider: AIProvider, prompt_path: Path | None = None) -> None:
        self.provider = provider
        self.prompt_path = prompt_path or Path(__file__).parent / "prompts/event_v1.md"

    async def synthesize(self, articles: list[Article], minimum_sources: int) -> EventSynthesis:
        prompt = self._prompt(articles)
        try:
            result = await self.provider.generate(prompt, EventSynthesis)
        except Exception as exc:
            print(f"[AI] generate failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            raise
        errors = validate_synthesis(result, articles, minimum_sources)
        if not errors:
            return result

        repair = (
            f"{prompt}\n\nVALIDATION ERRORS:\n- "
            + "\n- ".join(errors)
            + "\nИсправь только перечисленные ошибки и снова верни объект по той же schema."
        )
        result = await self.provider.generate(repair, EventSynthesis)
        errors = validate_synthesis(result, articles, minimum_sources)
        if errors:
            raise InvalidSynthesisError("; ".join(errors))
        return result

    def _prompt(self, articles: list[Article]) -> str:
        policy = self.prompt_path.read_text(encoding="utf-8")
        input_payload = [
            {
                "article_id": article.id,
                "source_id": article.source_id,
                "title": article.title,
                "excerpt": article.excerpt,
                "published_at": article.published_at.isoformat() if article.published_at else None,
            }
            for article in articles
        ]
        return f"{policy}\n\nINPUT:\n{json.dumps(input_payload, ensure_ascii=False)}"
