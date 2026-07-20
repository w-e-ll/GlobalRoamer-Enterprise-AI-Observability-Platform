from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.workers.outbox_publisher import (
    OutboxPublisher,
)


def make_event(
    *,
    event_type: str = "trace.parsed",
    event_version: int = 1,
    correlation_id: str = "correlation-001",
    tenant_id: str = "test-tenant",
    producer: str = "pytest",
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_type=event_type,
        event_version=event_version,
        correlation_id=correlation_id,
        causation_id=None,
        tenant_id=tenant_id,
        occurred_at=datetime.now(timezone.utc),
        producer=producer,
        payload={
            "trace_id": "trace-001",
        },
    )


@pytest.mark.anyio
async def test_publish_delegates_event_to_transport() -> None:
    transport = AsyncMock()

    publisher = OutboxPublisher(
        event_publisher=transport,
    )

    event = make_event()

    await publisher.publish(event)

    transport.publish.assert_awaited_once_with(event)


@pytest.mark.anyio
async def test_publish_rejects_empty_event_type() -> None:
    transport = AsyncMock()

    publisher = OutboxPublisher(
        event_publisher=transport,
    )

    event = make_event(
        event_type="   ",
    )

    with pytest.raises(
        ValueError,
        match="event_type must not be empty",
    ):
        await publisher.publish(event)

    transport.publish.assert_not_awaited()


@pytest.mark.anyio
async def test_publish_rejects_invalid_event_version() -> None:
    transport = AsyncMock()

    publisher = OutboxPublisher(
        event_publisher=transport,
    )

    event = make_event(
        event_version=0,
    )

    with pytest.raises(
        ValueError,
        match="event_version must be greater than zero",
    ):
        await publisher.publish(event)

    transport.publish.assert_not_awaited()


@pytest.mark.anyio
async def test_publish_rejects_empty_correlation_id() -> None:
    transport = AsyncMock()

    publisher = OutboxPublisher(
        event_publisher=transport,
    )

    event = make_event(
        correlation_id="   ",
    )

    with pytest.raises(
        ValueError,
        match="correlation_id must not be empty",
    ):
        await publisher.publish(event)

    transport.publish.assert_not_awaited()


@pytest.mark.anyio
async def test_publish_rejects_empty_tenant_id() -> None:
    transport = AsyncMock()

    publisher = OutboxPublisher(
        event_publisher=transport,
    )

    event = make_event(
        tenant_id="   ",
    )

    with pytest.raises(
        ValueError,
        match="tenant_id must not be empty",
    ):
        await publisher.publish(event)

    transport.publish.assert_not_awaited()


@pytest.mark.anyio
async def test_publish_rejects_empty_producer() -> None:
    transport = AsyncMock()

    publisher = OutboxPublisher(
        event_publisher=transport,
    )

    event = make_event(
        producer="   ",
    )

    with pytest.raises(
        ValueError,
        match="producer must not be empty",
    ):
        await publisher.publish(event)

    transport.publish.assert_not_awaited()


@pytest.mark.anyio
async def test_publish_propagates_transport_failure() -> None:
    transport = AsyncMock()

    transport.publish.side_effect = RuntimeError(
        "Broker is unavailable"
    )

    publisher = OutboxPublisher(
        event_publisher=transport,
    )

    event = make_event()

    with pytest.raises(
        RuntimeError,
        match="Broker is unavailable",
    ):
        await publisher.publish(event)

    transport.publish.assert_awaited_once_with(event)


@pytest.mark.anyio
async def test_publish_many_preserves_event_order() -> None:
    published_events: list[EventEnvelope] = []

    async def capture_event(
        event: EventEnvelope,
    ) -> None:
        published_events.append(event)

    transport = AsyncMock()
    transport.publish.side_effect = capture_event

    publisher = OutboxPublisher(
        event_publisher=transport,
    )

    first_event = make_event(
        correlation_id="correlation-001",
    )
    second_event = make_event(
        correlation_id="correlation-002",
    )
    third_event = make_event(
        correlation_id="correlation-003",
    )

    await publisher.publish_many(
        [
            first_event,
            second_event,
            third_event,
        ]
    )

    assert published_events == [
        first_event,
        second_event,
        third_event,
    ]

    assert transport.publish.await_count == 3


@pytest.mark.anyio
async def test_publish_many_stops_after_first_failure() -> None:
    first_event = make_event(
        correlation_id="correlation-001",
    )
    second_event = make_event(
        correlation_id="correlation-002",
    )
    third_event = make_event(
        correlation_id="correlation-003",
    )

    transport = AsyncMock()

    transport.publish.side_effect = [
        None,
        RuntimeError("Second event failed"),
        None,
    ]

    publisher = OutboxPublisher(
        event_publisher=transport,
    )

    with pytest.raises(
        RuntimeError,
        match="Second event failed",
    ):
        await publisher.publish_many(
            [
                first_event,
                second_event,
                third_event,
            ]
        )

    assert transport.publish.await_count == 2

    published_events = [
        call.args[0]
        for call in transport.publish.await_args_list
    ]

    assert published_events == [
        first_event,
        second_event,
    ]
