from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from trends.domain.enums import SourceState
from trends.domain.models import RawArticle, SourceConfig


@dataclass(frozen=True)
class CollectContext:
    started_at: datetime
    query_terms: tuple[str, ...] = ()


@dataclass
class CollectorResult:
    articles: list[RawArticle] = field(default_factory=list)
    state: SourceState = SourceState.AVAILABLE
    latency_ms: int | None = None
    error_code: str | None = None


class Collector(Protocol):
    async def collect(self, context: CollectContext, config: SourceConfig) -> CollectorResult: ...

