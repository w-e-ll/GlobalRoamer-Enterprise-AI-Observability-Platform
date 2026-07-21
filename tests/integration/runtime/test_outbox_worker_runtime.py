"""End-to-end integration tests for the production outbox worker runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from globalroamer_platform.bootstrap.runtime import (
    build_application_runtime,
)
from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
    OutboxMessageStatus,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
)
from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)
from globalroamer_platform.infrastructure.messaging.in_memory_event_publisher import (
    InMemoryEventPublisher,
)
from globalroamer_platform.workers.outbox_worker import (
    OutboxWorkerSettings,
)


async def persist_pending_message() -> OutboxMessage:
    """Persist one immediately available outbox message."""
    event = EventEnvelope(
        event_id=uuid4(),
        event_type="trace.parsed",
        event_version=1,
        correlation_id=str(uuid4()),
        causation_id=None,
        tenant_id=f"runtime-test-{uuid4()}",
        occurred_at=datetime.now(timezone.utc),
        producer="pytest.integration.runtime",
        payload={
            "trace_id": f"trace-{uuid4()}",
            "testcase_id": "TC-001",
        },
    )

    message = OutboxMessage.create(
        event=event,
        available_at=datetime.now(timezone.utc),
    )

    async with async_session_factory() as session:
        repository = SQLAlchemyOutboxRepository(session)
        await repository.add(message)
        await session.commit()

    return message


async def load_message(
    message_id: UUID,
) -> OutboxMessage:
    """Reload an outbox message in a fresh database session."""
    async with async_session_factory() as session:
        repository = SQLAlchemyOutboxRepository(session)
        message = await repository.get_by_id(message_id)

    assert message is not None
    return message


async def wait_until(
    predicate: Callable[[], Awaitable[bool]],
    *,
    timeout_seconds: float = 2.0,
    interval_seconds: float = 0.01,
) -> None:
    """Wait until an asynchronous predicate becomes true."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds

    while loop.time() < deadline:
        if await predicate():
            return

        await asyncio.sleep(interval_seconds)

    raise TimeoutError(
        f"condition was not met within {timeout_seconds} seconds"
    )


@pytest.mark.asyncio
async def test_outbox_runtime_publishes_and_commits_pending_message() -> None:
    """
    The managed runtime publishes a pending message and commits its state.

    This verifies the full production path:

    ApplicationRuntime
        -> OutboxWorker
        -> SessionScopedOutboxPublisher
        -> PublishPendingOutboxMessages
        -> SQLAlchemyOutboxRepository
        -> commit
    """
    message = await persist_pending_message()
    event_publisher = InMemoryEventPublisher()

    runtime = build_application_runtime(
        session_factory=async_session_factory,
        event_publisher=event_publisher,
        outbox_settings=OutboxWorkerSettings(
            poll_interval_seconds=0.01,
            batch_size=100,
            max_attempts=5,
            initial_retry_delay_seconds=0.01,
        ),
        shutdown_timeout_seconds=1.0,
    )

    async def message_was_published() -> bool:
        stored_message = await load_message(message.id)

        return (
            stored_message.status == OutboxMessageStatus.PUBLISHED
            and any(
                event.event_id == message.event_id
                for event in event_publisher.events
            )
        )

    await runtime.start()

    try:
        await wait_until(
            message_was_published,
            timeout_seconds=2.0,
        )
    finally:
        await runtime.stop()

    stored_message = await load_message(message.id)

    assert stored_message.status == OutboxMessageStatus.PUBLISHED
    assert stored_message.attempt_count == 1
    assert stored_message.published_at is not None
    assert stored_message.last_attempt_at is not None
    assert stored_message.last_error is None

    published_event_ids = {
        event.event_id
        for event in event_publisher.events
    }

    assert message.event_id in published_event_ids
    assert runtime.is_started is False
    assert runtime.is_stopping is False
