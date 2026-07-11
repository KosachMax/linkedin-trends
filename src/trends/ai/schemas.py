from pydantic import BaseModel, ConfigDict, Field


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
    status: str
    article_ids: list[str] = Field(min_length=1)
    facts: list[AIFact] = Field(min_length=1)

