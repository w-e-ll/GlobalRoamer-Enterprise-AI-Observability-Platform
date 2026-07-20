from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.infrastructure.messaging.in_memory_event_publisher import (
    InMemoryEventPublisher,
)


def make_event(
    *,
    correlation_id: str = "correlation-001",
    event_type: str = "trace.parsed",
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_type=event_type,
        event_version=1,
        correlation_id=correlation_id,
        causation_id=None,
        tenant_id="test-tenant",
        occurred_at=datetime.now(timezone.utc),
        producer="pytest",
        payload={
            "trace_id": "trace-001",
        },
    )


@pytest.mark.anyio
async def test_publish_stores_event() -> None:
    publisher = InMemoryEventPublisher()
    event = make_event()

    await publisher.publish(event)

    assert publisher.event_count == 1
    assert publisher.events == (event,)
    assert publisher.last_event() == event


@pytest.mark.anyio
async def test_publish_preserves_event_order() -> None:
    publisher = InMemoryEventPublisher()

    first_event = make_event(
        correlation_id="correlation-001",
    )
    second_event = make_event(
        correlation_id="correlation-002",
    )
    third_event = make_event(
        correlation_id="correlation-003",
    )

    await publisher.publish(first_event)
    await publisher.publish(second_event)
    await publisher.publish(third_event)

    assert publisher.event_count == 3
    assert publisher.events == (
        first_event,
        second_event,
        third_event,
    )
    assert publisher.last_event() == third_event


def test_new_publisher_is_empty() -> None:
    publisher = InMemoryEventPublisher()

    assert publisher.event_count == 0
    assert publisher.events == ()
    assert publisher.last_event() is None


@pytest.mark.anyio
async def test_clear_removes_all_events() -> None:
    publisher = InMemoryEventPublisher()

    await publisher.publish(make_event())
    await publisher.publish(
        make_event(
            correlation_id="correlation-002",
        )
    )

    assert publisher.event_count == 2

    publisher.clear()

    assert publisher.event_count == 0
    assert publisher.events == ()
    assert publisher.last_event() is None


@pytest.mark.anyio
async def test_events_returns_immutable_snapshot() -> None:
    publisher = InMemoryEventPublisher()
    first_event = make_event()

    await publisher.publish(first_event)

    snapshot = publisher.events

    second_event = make_event(
        correlation_id="correlation-002",
    )
    await publisher.publish(second_event)

    assert snapshot == (first_event,)
    assert publisher.events == (
        first_event,
        second_event,
    )


@pytest.mark.anyio
async def test_same_event_can_be_published_more_than_once() -> None:
    publisher = InMemoryEventPublisher()
    event = make_event()

    await publisher.publish(event)
    await publisher.publish(event)

    assert publisher.event_count == 2
    assert publisher.events == (
        event,
        event,
    )
