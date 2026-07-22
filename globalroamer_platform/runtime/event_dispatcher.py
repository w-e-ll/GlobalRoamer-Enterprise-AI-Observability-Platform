"""In-process event dispatcher for routing integration events."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Protocol

from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)


class EventHandler(Protocol):
    """Application event handler."""

    async def handle(
        self,
        event: EventEnvelope,
    ) -> EventEnvelope | None:
        """
        Process one event.

        Returns a follow-up event when the handler produces one,
        otherwise returns None.
        """
        ...


AsyncEventHandler = Callable[
    [EventEnvelope],
    Awaitable[EventEnvelope | None],
]


class EventDispatcher:
    """Dispatch events to registered handlers."""

    def __init__(self) -> None:
        self._handlers: dict[
            str,
            list[AsyncEventHandler],
        ] = defaultdict(list)

    def register(
        self,
        *,
        event_type: str,
        handler: AsyncEventHandler,
    ) -> None:
        """Register one handler for an event type."""
        normalized = event_type.strip()

        if not normalized:
            raise ValueError(
                "event_type must not be empty",
            )

        self._handlers[normalized].append(handler)

    async def dispatch(
        self,
        event: EventEnvelope,
    ) -> list[EventEnvelope]:
        """
        Dispatch an event.

        Returns all follow-up events produced by handlers.
        """
        produced: list[EventEnvelope] = []

        handlers = self._handlers.get(
            event.event_type,
            (),
        )

        for handler in handlers:
            next_event = await handler(event)

            if next_event is not None:
                produced.append(next_event)

        return produced

    @property
    def registered_event_types(
        self,
    ) -> tuple[str, ...]:
        """Return registered event types."""
        return tuple(
            sorted(self._handlers.keys())
        )

    def clear(self) -> None:
        """Remove all registered handlers."""
        self._handlers.clear()
