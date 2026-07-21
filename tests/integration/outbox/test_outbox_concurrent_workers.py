# tests/integration/outbox/test_outbox_concurrent_workers.py

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from globalroamer_platform.application.outbox.publish_pending_outbox_messages import (
    PublishPendingOutboxMessages,
    PublishPendingOutboxMessagesCommand,
    PublishPendingOutboxMessagesResult,
)
from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
    OutboxMessageStatus,
)
from globalroamer_platform.domain.events.event_envelope import EventEnvelope
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
)
from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)


TEST_AVAILABLE_AT = datetime(
    1970,
    1,
    1,
    tzinfo=timezone.utc,
)

TEST_CLOCK = datetime(
    2026,
    7,
    21,
    13,
    0,
    0,
    tzinfo=timezone.utc,
)


class BlockingRecordingEventPublisher:
    """Publisher that keeps the first worker transaction open.

    The publisher signals when publication starts and then waits until the
    test releases it. While it waits, the first worker still owns the
    PostgreSQL row lock acquired by ``FOR UPDATE SKIP LOCKED``.
    """

    def __init__(self) -> None:
        self.publication_started = asyncio.Event()
        self.allow_publication_to_finish = asyncio.Event()
        self.published_events: list[EventEnvelope] = []

    async def publish(
        self,
        event: EventEnvelope,
    ) -> None:
        self.publication_started.set()

        await self.allow_publication_to_finish.wait()

        self.published_events.append(event)


class RecordingEventPublisher:
    """Publisher that records all events passed to it."""

    def __init__(self) -> None:
        self.published_events: list[EventEnvelope] = []

    async def publish(
        self,
        event: EventEnvelope,
    ) -> None:
        self.published_events.append(event)


@dataclass(frozen=True, slots=True)
class WorkerExecution:
    """Result and events produced by one worker execution."""

    result: PublishPendingOutboxMessagesResult
    published_events: list[EventEnvelope]


def create_event() -> EventEnvelope:
    """Create a unique event for the concurrency test."""

    return EventEnvelope(
        event_id=uuid4(),
        event_type="trace.parsed",
        event_version=1,
        correlation_id=str(uuid4()),
        causation_id=None,
        tenant_id=f"concurrent-outbox-{uuid4()}",
        occurred_at=TEST_CLOCK,
        producer="pytest.integration.outbox.concurrent",
        payload={
            "trace_id": f"trace-{uuid4()}",
            "testcase_id": "TC-CONCURRENT-001",
        },
    )


async def persist_pending_message() -> OutboxMessage:
    """Persist one pending message before starting both workers."""

    message = OutboxMessage.create(
        event=create_event(),
        available_at=TEST_AVAILABLE_AT,
    )

    async with async_session_factory() as session:
        repository = SQLAlchemyOutboxRepository(session)

        await repository.add(message)
        await session.commit()

    return message


async def load_message(
    message_id,
) -> OutboxMessage:
    """Reload an outbox message through a fresh session."""

    async with async_session_factory() as session:
        repository = SQLAlchemyOutboxRepository(session)
        message = await repository.get_by_id(message_id)

    assert message is not None
    return message


def create_command() -> PublishPendingOutboxMessagesCommand:
    """Create the command used by both competing workers."""

    return PublishPendingOutboxMessagesCommand(
        batch_size=1,
        max_attempts=5,
        initial_retry_delay_seconds=5.0,
    )


@pytest.mark.asyncio
async def test_concurrent_workers_publish_message_only_once() -> None:
    """Two workers must not select and publish the same outbox message."""

    message = await persist_pending_message()

    first_publisher = BlockingRecordingEventPublisher()
    second_publisher = RecordingEventPublisher()

    async def run_first_worker() -> WorkerExecution:
        async with async_session_factory() as session:
            repository = SQLAlchemyOutboxRepository(session)

            service = PublishPendingOutboxMessages(
                repository=repository,
                event_publisher=first_publisher,
                clock=lambda: TEST_CLOCK,
            )

            result = await service.execute(create_command())
            await session.commit()

        return WorkerExecution(
            result=result,
            published_events=list(
                first_publisher.published_events,
            ),
        )

    async def run_second_worker() -> WorkerExecution:
        async with async_session_factory() as session:
            repository = SQLAlchemyOutboxRepository(session)

            service = PublishPendingOutboxMessages(
                repository=repository,
                event_publisher=second_publisher,
                clock=lambda: TEST_CLOCK,
            )

            result = await service.execute(create_command())
            await session.commit()

        return WorkerExecution(
            result=result,
            published_events=list(
                second_publisher.published_events,
            ),
        )

    first_worker_task = asyncio.create_task(
        run_first_worker(),
    )

    try:
        await asyncio.wait_for(
            first_publisher.publication_started.wait(),
            timeout=2.0,
        )

        # The first transaction is still open and owns the row lock.
        # The second worker must skip the locked message rather than
        # selecting or publishing it.
        second_execution = await asyncio.wait_for(
            run_second_worker(),
            timeout=2.0,
        )
    finally:
        first_publisher.allow_publication_to_finish.set()

    first_execution = await asyncio.wait_for(
        first_worker_task,
        timeout=2.0,
    )

    stored_message = await load_message(message.id)

    total_selected_count = (
        first_execution.result.selected_count
        + second_execution.result.selected_count
    )
    total_published_count = (
        first_execution.result.published_count
        + second_execution.result.published_count
    )
    total_published_events = (
        first_execution.published_events
        + second_execution.published_events
    )

    assert first_execution.result.selected_count == 1
    assert first_execution.result.published_count == 1

    assert second_execution.result.selected_count == 0
    assert second_execution.result.published_count == 0
    assert second_execution.result.retry_scheduled_count == 0
    assert second_execution.result.permanently_failed_count == 0

    assert total_selected_count == 1
    assert total_published_count == 1
    assert len(total_published_events) == 1

    assert total_published_events[0].event_id == message.event_id

    assert stored_message.status == OutboxMessageStatus.PUBLISHED
    assert stored_message.attempt_count == 1
    assert stored_message.published_at == TEST_CLOCK
    assert stored_message.last_attempt_at == TEST_CLOCK
    assert stored_message.last_error is None
