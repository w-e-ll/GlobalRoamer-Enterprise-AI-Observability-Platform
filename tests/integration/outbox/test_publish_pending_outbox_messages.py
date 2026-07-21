# tests/integration/outbox/test_publish_pending_outbox_messages.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from globalroamer_platform.application.outbox.publish_pending_outbox_messages import (
    PublishPendingOutboxMessages,
    PublishPendingOutboxMessagesCommand,
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
    2000,
    1,
    1,
    tzinfo=timezone.utc,
)

TEST_CLOCK = datetime(
    2026,
    7,
    21,
    12,
    0,
    0,
    tzinfo=timezone.utc,
)


class RecordingEventPublisher:
    """Event publisher that records successfully published events."""

    def __init__(self) -> None:
        self.published_events: list[EventEnvelope] = []

    async def publish(
        self,
        event: EventEnvelope,
    ) -> None:
        self.published_events.append(event)


class FailingEventPublisher:
    """Event publisher that always simulates a broker failure."""

    def __init__(
        self,
        error_message: str = "Kafka unavailable",
    ) -> None:
        self.error_message = error_message
        self.publish_attempts = 0

    async def publish(
        self,
        event: EventEnvelope,
    ) -> None:
        self.publish_attempts += 1
        raise RuntimeError(self.error_message)


def create_event(
    *,
    tenant_id: str,
    trace_id: str,
) -> EventEnvelope:
    """Create a unique event envelope for an integration test."""

    return EventEnvelope(
        event_id=uuid4(),
        event_type="trace.parsed",
        event_version=1,
        correlation_id=str(uuid4()),
        causation_id=None,
        tenant_id=tenant_id,
        occurred_at=TEST_CLOCK,
        producer="pytest.integration.outbox",
        payload={
            "trace_id": trace_id,
            "testcase_id": "TC-001",
        },
    )


async def persist_message(
    *,
    tenant_id: str,
    trace_id: str,
    available_at: datetime = TEST_AVAILABLE_AT,
) -> OutboxMessage:
    """Persist and commit one pending outbox message."""

    message = OutboxMessage.create(
        event=create_event(
            tenant_id=tenant_id,
            trace_id=trace_id,
        ),
        available_at=available_at,
    )

    async with async_session_factory() as session:
        repository = SQLAlchemyOutboxRepository(session)

        await repository.add(message)
        await session.commit()

    return message


async def load_message(
    message_id,
) -> OutboxMessage:
    """Reload an outbox message using a new database session."""

    async with async_session_factory() as session:
        repository = SQLAlchemyOutboxRepository(session)
        message = await repository.get_by_id(message_id)

    assert message is not None
    return message


@pytest.mark.asyncio
async def test_publishes_pending_outbox_message_successfully() -> None:
    """A pending message is published and marked as published."""

    tenant_id = f"publish-success-{uuid4()}"

    message = await persist_message(
        tenant_id=tenant_id,
        trace_id=f"trace-{uuid4()}",
    )

    event_publisher = RecordingEventPublisher()

    async with async_session_factory() as session:
        repository = SQLAlchemyOutboxRepository(session)

        service = PublishPendingOutboxMessages(
            repository=repository,
            event_publisher=event_publisher,
            clock=lambda: TEST_CLOCK,
        )

        result = await service.execute(
            PublishPendingOutboxMessagesCommand(
                batch_size=1,
                max_attempts=5,
                initial_retry_delay_seconds=5.0,
            )
        )

        await session.commit()

    stored_message = await load_message(message.id)

    assert result.selected_count == 1
    assert result.published_count == 1
    assert result.retry_scheduled_count == 0
    assert result.permanently_failed_count == 0

    assert len(event_publisher.published_events) == 1
    assert event_publisher.published_events[0].event_id == message.event_id

    assert stored_message.status == OutboxMessageStatus.PUBLISHED
    assert stored_message.attempt_count == 1
    assert stored_message.published_at == TEST_CLOCK
    assert stored_message.last_attempt_at == TEST_CLOCK
    assert stored_message.last_error is None


@pytest.mark.asyncio
async def test_schedules_retry_when_event_publication_fails() -> None:
    """A temporary publishing failure keeps the message pending for retry."""

    tenant_id = f"publish-retry-{uuid4()}"

    message = await persist_message(
        tenant_id=tenant_id,
        trace_id=f"trace-{uuid4()}",
    )

    event_publisher = FailingEventPublisher(
        error_message="Kafka unavailable",
    )

    async with async_session_factory() as session:
        repository = SQLAlchemyOutboxRepository(session)

        service = PublishPendingOutboxMessages(
            repository=repository,
            event_publisher=event_publisher,
            clock=lambda: TEST_CLOCK,
        )

        result = await service.execute(
            PublishPendingOutboxMessagesCommand(
                batch_size=1,
                max_attempts=5,
                initial_retry_delay_seconds=5.0,
            )
        )

        await session.commit()

    stored_message = await load_message(message.id)

    assert result.selected_count == 1
    assert result.published_count == 0
    assert result.retry_scheduled_count == 1
    assert result.permanently_failed_count == 0

    assert event_publisher.publish_attempts == 1

    assert stored_message.status == OutboxMessageStatus.PENDING
    assert stored_message.attempt_count == 1
    assert stored_message.last_attempt_at == TEST_CLOCK
    assert stored_message.last_error == "Kafka unavailable"
    assert stored_message.published_at is None

    assert stored_message.available_at == (
        TEST_CLOCK + timedelta(seconds=5)
    )


@pytest.mark.asyncio
async def test_marks_message_failed_after_maximum_attempts() -> None:
    """A message becomes permanently failed when max attempts is reached."""

    tenant_id = f"publish-failed-{uuid4()}"

    message = await persist_message(
        tenant_id=tenant_id,
        trace_id=f"trace-{uuid4()}",
    )

    event_publisher = FailingEventPublisher(
        error_message="Kafka unavailable",
    )

    async with async_session_factory() as session:
        repository = SQLAlchemyOutboxRepository(session)

        service = PublishPendingOutboxMessages(
            repository=repository,
            event_publisher=event_publisher,
            clock=lambda: TEST_CLOCK,
        )

        result = await service.execute(
            PublishPendingOutboxMessagesCommand(
                batch_size=1,
                max_attempts=1,
                initial_retry_delay_seconds=5.0,
            )
        )

        await session.commit()

    stored_message = await load_message(message.id)

    assert result.selected_count == 1
    assert result.published_count == 0
    assert result.retry_scheduled_count == 0
    assert result.permanently_failed_count == 1

    assert event_publisher.publish_attempts == 1

    assert stored_message.status == OutboxMessageStatus.FAILED
    assert stored_message.attempt_count == 1
    assert stored_message.last_attempt_at == TEST_CLOCK
    assert stored_message.last_error == "Kafka unavailable"
    assert stored_message.published_at is None


@pytest.mark.asyncio
async def test_respects_outbox_batch_size() -> None:
    """Only the configured number of available messages is processed."""

    tenant_id = f"publish-batch-{uuid4()}"

    messages = []

    for index in range(3):
        message = await persist_message(
            tenant_id=tenant_id,
            trace_id=f"trace-{index}-{uuid4()}",
            available_at=(
                TEST_AVAILABLE_AT
                + timedelta(microseconds=index)
            ),
        )
        messages.append(message)

    event_publisher = RecordingEventPublisher()

    async with async_session_factory() as session:
        repository = SQLAlchemyOutboxRepository(session)

        service = PublishPendingOutboxMessages(
            repository=repository,
            event_publisher=event_publisher,
            clock=lambda: TEST_CLOCK,
        )

        result = await service.execute(
            PublishPendingOutboxMessagesCommand(
                batch_size=2,
                max_attempts=5,
                initial_retry_delay_seconds=5.0,
            )
        )

        await session.commit()

    stored_messages = [
        await load_message(message.id)
        for message in messages
    ]

    published_messages = [
        message
        for message in stored_messages
        if message.status == OutboxMessageStatus.PUBLISHED
    ]

    pending_messages = [
        message
        for message in stored_messages
        if message.status == OutboxMessageStatus.PENDING
    ]

    assert result.selected_count == 2
    assert result.published_count == 2
    assert result.retry_scheduled_count == 0
    assert result.permanently_failed_count == 0

    assert len(event_publisher.published_events) == 2
    assert len(published_messages) == 2
    assert len(pending_messages) == 1

    assert all(
        message.attempt_count == 1
        for message in published_messages
    )

    assert pending_messages[0].attempt_count == 0
    assert pending_messages[0].published_at is None
