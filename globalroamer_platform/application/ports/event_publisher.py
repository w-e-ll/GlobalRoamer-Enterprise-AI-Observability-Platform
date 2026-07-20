"""Application port for publishing event envelopes."""

from __future__ import annotations

from typing import Protocol

from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)


class EventPublisher(Protocol):
    """Publish domain event envelopes through an external transport."""

    async def publish(
        self,
        event: EventEnvelope,
    ) -> None:
        """Publish one event envelope."""
        ...
