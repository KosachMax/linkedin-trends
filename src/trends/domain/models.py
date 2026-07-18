from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from .enums import EventStatus, SourceState


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RawArticle(Model):
    id: str | None = None
    source_id: str
    source_name: str
    url: HttpUrl
    title: str = Field(min_length=3)
    excerpt: str | None = None
    published_at: datetime | None = None
    collected_at: datetime
    language: str = "en"
    topic_hints: list[str] = Field(default_factory=list)
    source_perspective: Literal[
        "international", "ukrainian", "russian", "club", "community", "technical", "unspecified"
    ] = "unspecified"
    source_ownership: Literal[
        "independent", "state", "public", "official", "commercial", "community", "unspecified"
    ] = "unspecified"
    source_disclosure: str | None = None
    source_trust_tier: Literal["primary", "major", "community"] = "major"
    engagement: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Article(Model):
    id: str
    source_id: str
    source_name: str
    canonical_url: HttpUrl
    title: str
    normalized_title: str
    excerpt: str | None = None
    published_at: datetime | None = None
    collected_at: datetime
    language: str
    topic_hints: list[str] = Field(default_factory=list)
    source_perspective: Literal[
        "international", "ukrainian", "russian", "club", "community", "technical", "unspecified"
    ] = "unspecified"
    source_ownership: Literal[
        "independent", "state", "public", "official", "commercial", "community", "unspecified"
    ] = "unspecified"
    source_disclosure: str | None = None
    source_trust_tier: Literal["primary", "major", "community"] = "major"
    entities: list[str] = Field(default_factory=list)
    engagement: int | None = None


class Fact(Model):
    text: str
    article_ids: list[str] = Field(min_length=1)


class EventUpdate(Model):
    at: datetime
    summary: str
    article_ids: list[str] = Field(default_factory=list)


class EventIdentity(Model):
    event_type: str = "news_event"
    primary_entities: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)
    occurred_at: datetime | None = None


class DigestEvent(Model):
    id: str
    slug: str
    title: str
    brief: str = Field(min_length=200)
    context: str
    why_it_matters: str
    importance: int = Field(ge=1, le=10)
    status: EventStatus = EventStatus.NEW
    verification_status: Literal[
        "standard",
        "single_source",
        "same_perspective",
        "cross_perspective",
        "independent_confirmation",
        "conflicting_accounts",
    ] = "standard"
    category: str
    article_ids: list[str] = Field(min_length=1)
    facts: list[Fact] = Field(default_factory=list)
    updates: list[EventUpdate] = Field(default_factory=list)
    identity: EventIdentity | None = None
    first_seen_at: datetime
    updated_at: datetime


class SourceRun(Model):
    source_id: str
    source_name: str
    state: SourceState
    fetched: int = Field(default=0, ge=0)
    accepted: int = Field(default=0, ge=0)
    represented_events: int = Field(default=0, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    history: list[int] = Field(default_factory=list, max_length=7)


class CurrencyRate(Model):
    pair: Literal["USD/RUB", "EUR/RUB", "CNY/RUB"]
    value: float = Field(gt=0)
    change_pct: float | None = None


class DailyPicture(Model):
    title: str = "Картина дня"
    body: str


class DailyDigest(Model):
    schema_version: int = 2
    digest_id: str
    date: date
    generated_at: datetime
    daily_picture: DailyPicture
    currencies: list[CurrencyRate] = Field(default_factory=list)
    sources: list[SourceRun] = Field(default_factory=list)
    articles: list[Article] = Field(default_factory=list)
    events: list[DigestEvent] = Field(default_factory=list)

    @property
    def source_health(self) -> float:
        if not self.sources:
            return 0
        weights = {
            SourceState.AVAILABLE: 1.0,
            SourceState.DEGRADED: 0.5,
            SourceState.UNAVAILABLE: 0.0,
        }
        return sum(weights[item.state] for item in self.sources) / len(self.sources)


class SourceConfig(Model):
    id: str
    title: str
    type: str
    enabled: bool = True
    url: HttpUrl | None = None
    language: str = "en"
    tags: list[str] = Field(default_factory=list)
    trust_tier: Literal["primary", "major", "community"] = "major"
    perspective: Literal[
        "international", "ukrainian", "russian", "club", "community", "technical", "unspecified"
    ] = "unspecified"
    ownership: Literal[
        "independent", "state", "public", "official", "commercial", "community", "unspecified"
    ] = "unspecified"
    editorial_note: str | None = None
    timeout_seconds: int = Field(default=15, ge=1, le=60)
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def rss_requires_url(self) -> SourceConfig:
        if self.type == "rss" and self.url is None:
            raise ValueError("RSS source requires url")
        return self


class TopicConfig(Model):
    include_any: list[str] = Field(default_factory=list)
    exclude_any: list[str] = Field(default_factory=list)
    entities: dict[str, list[str]] = Field(default_factory=dict)


class DigestSourceRules(Model):
    include_tags: list[str] = Field(default_factory=list)
    min_independent_sources: int = Field(default=2, ge=1)
    min_perspectives: int = Field(default=1, ge=1, le=3)
    allow_single_source_for: list[str] = Field(default_factory=list)


class DigestOutput(Model):
    max_events: int = Field(default=10, ge=1, le=50)
    daily_picture_min_chars: int = Field(default=500, ge=200)


class DedupeConfig(Model):
    lookback_hours: int = Field(default=72, ge=1, le=336)
    candidate_similarity: float = Field(default=0.72, ge=0, le=1)
    max_neighbors: int = Field(default=8, ge=1, le=50)
    max_bundle_size: int = Field(default=20, ge=2, le=100)
    event_match_confidence: float = Field(default=0.90, ge=0, le=1)
    final_audit_confidence: float = Field(default=0.95, ge=0, le=1)


class DigestProfile(Model):
    id: str
    title: str
    enabled: bool = True
    languages: list[str] = Field(default_factory=lambda: ["en"])
    topic: TopicConfig
    categories: list[str]
    sources: DigestSourceRules = Field(default_factory=DigestSourceRules)
    dedupe: DedupeConfig = Field(default_factory=DedupeConfig)
    ranking: dict[str, float] = Field(default_factory=dict)
    output: DigestOutput = Field(default_factory=DigestOutput)
