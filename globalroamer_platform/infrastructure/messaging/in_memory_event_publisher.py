"""In-memory implementation of the EventPublisher application port.

This adapter is intended for:

- local development;
- unit and integration tests;
- verifying event flow before introducing a real message broker.

It stores published events in memory and does not provide durability,
cross-process delivery, retries, or acknowledgements.
"""

from __future__ import annotations

from collections.abc import Sequence

from globalroamer_platform.application.ports.event_publisher import (
    EventPublisher,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)


class InMemoryEventPublisher(EventPublisher):
    """Store published event envelopes in memory."""

    def __init__(self) -> None:
        self._events: list[EventEnvelope] = []

    async def publish(
        self,
        event: EventEnvelope,
    ) -> None:
        """Store one published event."""
        self._events.append(event)

    @property
    def events(self) -> Sequence[EventEnvelope]:
        """Return published events as an immutable snapshot."""
        return tuple(self._events)

    @property
    def event_count(self) -> int:
        """Return the number of published events."""
        return len(self._events)

    def clear(self) -> None:
        """Remove all published events."""
        self._events.clear()

    def last_event(self) -> EventEnvelope | None:
        """Return the most recently published event."""
        if not self._events:
            return None

        return self._events[-1]
