from enum import StrEnum


class SourceState(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class EventStatus(StrEnum):
    NEW = "new"
    UPDATED = "updated"
    DISPUTED = "disputed"
    COMPLETED = "completed"

