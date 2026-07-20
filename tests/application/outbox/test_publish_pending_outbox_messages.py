from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
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
from globalroamer_platform.domain.events.event_types import TRACE_PARSED


FIXED_TIME = datetime(
    2026,
    7,
    20,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def make_event(
    *,
    trace_id: str = "trace-001",
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_type=TRACE_PARSED,
        event_version=1,
        correlation_id=f"corr-{trace_id}",
        causation_id=uuid4(),
        tenant_id="tenant-001",
        occurred_at=FIXED_TIME - timedelta(minutes=1),
        producer="pytest",
        payload={
            "trace_id": trace_id,
            "row_count": 100,
        },
    )


def make_message(
    *,
    trace_id: str = "trace-001",
    attempt_count: int = 0,
) -> OutboxMessage:
    message = OutboxMessage.create(
        event=make_event(trace_id=trace_id),
        available_at=FIXED_TIME - timedelta(seconds=1),
    )

    for attempt_number in range(attempt_count):
        message = message.mark_failed(
            error=f"previous failure {attempt_number + 1}",
            failed_at=(
                FIXED_TIME
                - timedelta(minutes=attempt_count - attempt_number)
            ),
            retry_at=FIXED_TIME - timedelta(seconds=1),
        )

    return message


def make_service(
    *,
    repository: AsyncMock | None = None,
    event_publisher: AsyncMock | None = None,
) -> tuple[
    PublishPendingOutboxMessages,
    AsyncMock,
    AsyncMock,
]:
    repository = repository or AsyncMock()
    event_publisher = event_publisher or AsyncMock()

    service = PublishPendingOutboxMessages(
        repository=repository,
        event_publisher=event_publisher,
        clock=lambda: FIXED_TIME,
    )

    return service, repository, event_publisher


def test_command_uses_default_configuration() -> None:
    command = PublishPendingOutboxMessagesCommand()

    assert command.batch_size == 100
    assert command.max_attempts == 5
    assert command.initial_retry_delay_seconds == 5.0


@pytest.mark.parametrize(
    ("field_name", "field_value", "expected_message"),
    [
        (
            "batch_size",
            0,
            "batch_size must be greater than zero",
        ),
        (
            "max_attempts",
            0,
            "max_attempts must be greater than zero",
        ),
        (
            "initial_retry_delay_seconds",
            0,
            "initial_retry_delay_seconds must be greater than zero",
        ),
    ],
)
def test_command_rejects_non_positive_configuration(
    field_name: str,
    field_value: int,
    expected_message: str,
) -> None:
    arguments = {
        "batch_size": 100,
        "max_attempts": 5,
        "initial_retry_delay_seconds": 5.0,
    }
    arguments[field_name] = field_value

    with pytest.raises(
        ValueError,
        match=expected_message,
    ):
        PublishPendingOutboxMessagesCommand(**arguments)


@pytest.mark.anyio
async def test_execute_returns_empty_result_when_no_messages_exist() -> None:
    service, repository, event_publisher = make_service()

    repository.list_available.return_value = []

    result = await service.execute(
        PublishPendingOutboxMessagesCommand(),
    )

    assert result.selected_count == 0
    assert result.published_count == 0
    assert result.retry_scheduled_count == 0
    assert result.permanently_failed_count == 0
    assert result.failed_count == 0

    repository.list_available.assert_awaited_once_with(
        available_before=FIXED_TIME,
        limit=100,
    )
    event_publisher.publish.assert_not_awaited()
    repository.update.assert_not_awaited()


@pytest.mark.anyio
async def test_execute_publishes_message_and_marks_it_published() -> None:
    service, repository, event_publisher = make_service()

    message = make_message()
    repository.list_available.return_value = [message]

    result = await service.execute(
        PublishPendingOutboxMessagesCommand(),
    )

    event_publisher.publish.assert_awaited_once_with(
        message.event,
    )
    repository.update.assert_awaited_once()

    updated_message = repository.update.await_args.args[0]

    assert updated_message.id == message.id
    assert updated_message.status == OutboxMessageStatus.PUBLISHED
    assert updated_message.attempt_count == 1
    assert updated_message.published_at == FIXED_TIME
    assert updated_message.last_attempt_at == FIXED_TIME
    assert updated_message.last_error is None

    assert result.selected_count == 1
    assert result.published_count == 1
    assert result.retry_scheduled_count == 0
    assert result.permanently_failed_count == 0
    assert result.failed_count == 0


@pytest.mark.anyio
async def test_execute_schedules_retry_after_publication_failure() -> None:
    service, repository, event_publisher = make_service()

    message = make_message()
    repository.list_available.return_value = [message]
    event_publisher.publish.side_effect = RuntimeError(
        "broker unavailable",
    )

    command = PublishPendingOutboxMessagesCommand(
        max_attempts=5,
        initial_retry_delay_seconds=5,
    )

    result = await service.execute(command)

    repository.update.assert_awaited_once()

    updated_message = repository.update.await_args.args[0]

    assert updated_message.status == OutboxMessageStatus.PENDING
    assert updated_message.attempt_count == 1
    assert updated_message.last_attempt_at == FIXED_TIME
    assert updated_message.last_error == "broker unavailable"
    assert updated_message.available_at == (
        FIXED_TIME + timedelta(seconds=5)
    )
    assert updated_message.published_at is None

    assert result.selected_count == 1
    assert result.published_count == 0
    assert result.retry_scheduled_count == 1
    assert result.permanently_failed_count == 0
    assert result.failed_count == 1


@pytest.mark.anyio
async def test_execute_uses_exponential_retry_delay() -> None:
    service, repository, event_publisher = make_service()

    message = make_message(
        attempt_count=2,
    )

    repository.list_available.return_value = [message]
    event_publisher.publish.side_effect = RuntimeError(
        "temporary failure",
    )

    await service.execute(
        PublishPendingOutboxMessagesCommand(
            max_attempts=5,
            initial_retry_delay_seconds=5,
        ),
    )

    updated_message = repository.update.await_args.args[0]

    assert updated_message.attempt_count == 3
    assert updated_message.status == OutboxMessageStatus.PENDING
    assert updated_message.available_at == (
        FIXED_TIME + timedelta(seconds=20)
    )


@pytest.mark.anyio
async def test_execute_marks_message_permanently_failed_at_max_attempts() -> None:
    service, repository, event_publisher = make_service()

    message = make_message(
        attempt_count=4,
    )

    repository.list_available.return_value = [message]
    event_publisher.publish.side_effect = RuntimeError(
        "broker rejected event",
    )

    result = await service.execute(
        PublishPendingOutboxMessagesCommand(
            max_attempts=5,
        ),
    )

    updated_message = repository.update.await_args.args[0]

    assert updated_message.status == OutboxMessageStatus.FAILED
    assert updated_message.attempt_count == 5
    assert updated_message.last_attempt_at == FIXED_TIME
    assert updated_message.last_error == "broker rejected event"
    assert updated_message.published_at is None

    assert result.selected_count == 1
    assert result.published_count == 0
    assert result.retry_scheduled_count == 0
    assert result.permanently_failed_count == 1
    assert result.failed_count == 1


@pytest.mark.anyio
async def test_execute_uses_exception_class_for_empty_error_message() -> None:
    service, repository, event_publisher = make_service()

    message = make_message()

    repository.list_available.return_value = [message]
    event_publisher.publish.side_effect = RuntimeError()

    await service.execute(
        PublishPendingOutboxMessagesCommand(),
    )

    updated_message = repository.update.await_args.args[0]

    assert updated_message.last_error == "RuntimeError"
    assert updated_message.status == OutboxMessageStatus.PENDING


@pytest.mark.anyio
async def test_execute_processes_mixed_batch() -> None:
    service, repository, event_publisher = make_service()

    first_message = make_message(
        trace_id="trace-001",
    )
    second_message = make_message(
        trace_id="trace-002",
    )
    third_message = make_message(
        trace_id="trace-003",
        attempt_count=4,
    )

    repository.list_available.return_value = [
        first_message,
        second_message,
        third_message,
    ]

    event_publisher.publish.side_effect = [
        None,
        RuntimeError("temporary broker failure"),
        RuntimeError("permanent broker failure"),
    ]

    result = await service.execute(
        PublishPendingOutboxMessagesCommand(
            max_attempts=5,
        ),
    )

    assert event_publisher.publish.await_count == 3
    assert repository.update.await_count == 3

    updated_messages = [
        call.args[0]
        for call in repository.update.await_args_list
    ]

    assert updated_messages[0].status == OutboxMessageStatus.PUBLISHED
    assert updated_messages[0].attempt_count == 1

    assert updated_messages[1].status == OutboxMessageStatus.PENDING
    assert updated_messages[1].attempt_count == 1
    assert (
        updated_messages[1].last_error
        == "temporary broker failure"
    )

    assert updated_messages[2].status == OutboxMessageStatus.FAILED
    assert updated_messages[2].attempt_count == 5
    assert (
        updated_messages[2].last_error
        == "permanent broker failure"
    )

    assert result.selected_count == 3
    assert result.published_count == 1
    assert result.retry_scheduled_count == 1
    assert result.permanently_failed_count == 1
    assert result.failed_count == 2


@pytest.mark.anyio
async def test_execute_forwards_batch_size_to_repository() -> None:
    service, repository, _ = make_service()

    repository.list_available.return_value = []

    await service.execute(
        PublishPendingOutboxMessagesCommand(
            batch_size=25,
        ),
    )

    repository.list_available.assert_awaited_once_with(
        available_before=FIXED_TIME,
        limit=25,
    )


def test_calculate_retry_delay_uses_exponential_backoff() -> None:
    assert PublishPendingOutboxMessages._calculate_retry_delay(
        attempt_count=1,
        initial_delay_seconds=5,
    ) == timedelta(seconds=5)

    assert PublishPendingOutboxMessages._calculate_retry_delay(
        attempt_count=2,
        initial_delay_seconds=5,
    ) == timedelta(seconds=10)

    assert PublishPendingOutboxMessages._calculate_retry_delay(
        attempt_count=3,
        initial_delay_seconds=5,
    ) == timedelta(seconds=20)

    assert PublishPendingOutboxMessages._calculate_retry_delay(
        attempt_count=4,
        initial_delay_seconds=5,
    ) == timedelta(seconds=40)
