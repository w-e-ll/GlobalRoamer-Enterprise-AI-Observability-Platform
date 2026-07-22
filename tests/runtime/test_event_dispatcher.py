from __future__ import annotations

import pytest

from datetime import UTC, datetime
from uuid import UUID

from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.runtime.event_dispatcher import (
    EventDispatcher,
)


def make_event(
    event_type: str,
    *,
    event_id: UUID = UUID(
        "00000000-0000-0000-0000-000000000001"
    ),
) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id,
        event_type=event_type,
        correlation_id="correlation-1",
        tenant_id="tenant-1",
        occurred_at=datetime.now(UTC),
        producer="test-suite",
        payload={},
    )


@pytest.mark.asyncio
async def test_dispatch_calls_registered_handler() -> None:
    dispatcher = EventDispatcher()
    received: list[EventEnvelope] = []

    async def handler(
        event: EventEnvelope,
    ) -> EventEnvelope | None:
        received.append(event)
        return None

    dispatcher.register(
        event_type="TRACE_PARSED",
        handler=handler,
    )

    event = make_event("TRACE_PARSED")

    produced = await dispatcher.dispatch(event)

    assert received == [event]
    assert produced == []


@pytest.mark.asyncio
async def test_dispatch_returns_produced_events() -> None:
    dispatcher = EventDispatcher()

    produced_event = make_event(
        "TRACE_NORMALIZED",
        event_id=UUID(
            "00000000-0000-0000-0000-000000000002"
        ),
    )

    async def handler(
        _event: EventEnvelope,
    ) -> EventEnvelope | None:
        return produced_event

    dispatcher.register(
        event_type="TRACE_PARSED",
        handler=handler,
    )

    result = await dispatcher.dispatch(
        make_event("TRACE_PARSED"),
    )

    assert result == [produced_event]


@pytest.mark.asyncio
async def test_dispatch_calls_multiple_handlers_in_registration_order() -> None:
    dispatcher = EventDispatcher()
    calls: list[str] = []

    async def first_handler(
        _event: EventEnvelope,
    ) -> EventEnvelope | None:
        calls.append("first")
        return None

    async def second_handler(
        _event: EventEnvelope,
    ) -> EventEnvelope | None:
        calls.append("second")
        return None

    dispatcher.register(
        event_type="TRACE_PARSED",
        handler=first_handler,
    )
    dispatcher.register(
        event_type="TRACE_PARSED",
        handler=second_handler,
    )

    await dispatcher.dispatch(
        make_event("TRACE_PARSED"),
    )

    assert calls == ["first", "second"]


@pytest.mark.asyncio
async def test_dispatch_unknown_event_returns_empty_result() -> None:
    dispatcher = EventDispatcher()

    result = await dispatcher.dispatch(
        make_event("UNKNOWN_EVENT"),
    )

    assert result == []


def test_register_rejects_empty_event_type() -> None:
    dispatcher = EventDispatcher()

    async def handler(
        _event: EventEnvelope,
    ) -> EventEnvelope | None:
        return None

    with pytest.raises(
        ValueError,
        match="event_type must not be empty",
    ):
        dispatcher.register(
            event_type="   ",
            handler=handler,
        )


def test_registered_event_types_are_sorted() -> None:
    dispatcher = EventDispatcher()

    async def handler(
        _event: EventEnvelope,
    ) -> EventEnvelope | None:
        return None

    dispatcher.register(
        event_type="TRACE_NORMALIZED",
        handler=handler,
    )
    dispatcher.register(
        event_type="TRACE_PARSED",
        handler=handler,
    )

    assert dispatcher.registered_event_types == (
        "TRACE_NORMALIZED",
        "TRACE_PARSED",
    )


def test_clear_removes_registered_handlers() -> None:
    dispatcher = EventDispatcher()

    async def handler(
        _event: EventEnvelope,
    ) -> EventEnvelope | None:
        return None

    dispatcher.register(
        event_type="TRACE_PARSED",
        handler=handler,
    )

    dispatcher.clear()

    assert dispatcher.registered_event_types == ()
