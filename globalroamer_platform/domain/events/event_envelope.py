# domain/events/event_envelope.py

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: UUID
    event_type: str
    event_version: int = 1

    correlation_id: str
    causation_id: UUID | None = None
    tenant_id: str

    occurred_at: datetime
    producer: str

    payload: dict[str, Any] = Field(default_factory=dict)
