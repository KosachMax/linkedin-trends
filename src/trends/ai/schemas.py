from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


EventRelation = Literal["same_event", "update_of", "related", "different"]


class AIEventIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str = "news_event"
    primary_entities: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)
    occurred_at: datetime | None = None


class AIFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    article_ids: list[str] = Field(min_length=1)


class EventSynthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    brief: str = Field(min_length=200, max_length=800)
    context: str = Field(min_length=200)
    why_it_matters: str = Field(min_length=150)
    category: str
    impact: int = Field(ge=1, le=10)
    status: Literal["new", "updated", "disputed", "completed"]
    article_ids: list[str] = Field(min_length=1)
    facts: list[AIFact] = Field(min_length=1)
    identity: AIEventIdentity = Field(default_factory=AIEventIdentity)


class ArticlePartitionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    article_ids: list[str] = Field(min_length=1)


class ArticleRelationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left_article_id: str
    right_article_id: str
    relation: EventRelation
    confidence: float = Field(ge=0, le=1)


class ArticlePartition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    groups: list[ArticlePartitionGroup] = Field(min_length=1)
    relations: list[ArticleRelationDecision] = Field(default_factory=list)


class EventRelationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left_event_id: str
    right_event_id: str
    relation: EventRelation
    confidence: float = Field(ge=0, le=1)


class EventRelationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decisions: list[EventRelationDecision] = Field(default_factory=list)


class FeedAuditGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_ids: list[str] = Field(min_length=2)
    relation: Literal["same_event", "update_of"]
    confidence: float = Field(ge=0, le=1)


class FeedAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duplicate_groups: list[FeedAuditGroup] = Field(default_factory=list)
