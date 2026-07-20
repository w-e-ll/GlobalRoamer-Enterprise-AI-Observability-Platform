from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
    OutboxMessageStatus,
)
from globalroamer_platform.domain.events.event_envelope import EventEnvelope
from globalroamer_platform.domain.events.event_types import TRACE_PARSED


def make_event() -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_type=TRACE_PARSED,
        event_version=1,
        correlation_id="corr-001",
        causation_id=uuid4(),
        tenant_id="tenant-001",
        occurred_at=datetime.now(timezone.utc),
        producer="pytest",
        payload={
            "trace_id": "trace-001",
            "row_count": 100,
        },
    )


def test_create_returns_pending_message() -> None:
    event = make_event()

    message = OutboxMessage.create(event=event)

    assert message.event == event
    assert message.status == OutboxMessageStatus.PENDING
    assert message.attempt_count == 0
    assert message.published_at is None
    assert message.last_attempt_at is None
    assert message.last_error is None


def test_create_uses_requested_available_at() -> None:
    available_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    message = OutboxMessage.create(
        event=make_event(),
        available_at=available_at,
    )

    assert message.available_at == available_at


def test_event_properties_are_exposed() -> None:
    event = make_event()
    message = OutboxMessage.create(event=event)

    assert message.event_id == event.event_id
    assert message.event_type == event.event_type
    assert message.tenant_id == event.tenant_id
    assert message.correlation_id == event.correlation_id
    assert message.payload == event.payload


def test_pending_message_is_available_at_requested_time() -> None:
    now = datetime.now(timezone.utc)

    message = OutboxMessage.create(
        event=make_event(),
        available_at=now,
    )

    assert message.is_available(at=now) is True


def test_pending_message_is_not_available_before_available_at() -> None:
    now = datetime.now(timezone.utc)

    message = OutboxMessage.create(
        event=make_event(),
        available_at=now + timedelta(minutes=5),
    )

    assert message.is_available(at=now) is False


def test_mark_attempted_increments_attempt_count() -> None:
    attempted_at = datetime.now(timezone.utc)
    message = OutboxMessage.create(event=make_event())

    updated = message.mark_attempted(
        attempted_at=attempted_at,
    )

    assert updated.attempt_count == 1
    assert updated.last_attempt_at == attempted_at
    assert message.attempt_count == 0


def test_mark_published_updates_status() -> None:
    published_at = datetime.now(timezone.utc)
    message = OutboxMessage.create(event=make_event())

    updated = message.mark_published(
        published_at=published_at,
    )

    assert updated.status == OutboxMessageStatus.PUBLISHED
    assert updated.published_at == published_at
    assert updated.last_attempt_at == published_at
    assert updated.last_error is None
    assert updated.is_available(at=published_at) is False


def test_mark_failed_with_retry_keeps_message_pending() -> None:
    failed_at = datetime.now(timezone.utc)
    retry_at = failed_at + timedelta(minutes=1)
    message = OutboxMessage.create(event=make_event())

    updated = message.mark_failed(
        error="broker unavailable",
        retry_at=retry_at,
        failed_at=failed_at,
    )

    assert updated.status == OutboxMessageStatus.PENDING
    assert updated.attempt_count == 1
    assert updated.available_at == retry_at
    assert updated.last_attempt_at == failed_at
    assert updated.last_error == "broker unavailable"


def test_mark_failed_without_retry_marks_message_failed() -> None:
    failed_at = datetime.now(timezone.utc)
    message = OutboxMessage.create(event=make_event())

    updated = message.mark_failed(
        error="permanent transport error",
        failed_at=failed_at,
    )

    assert updated.status == OutboxMessageStatus.FAILED
    assert updated.attempt_count == 1
    assert updated.last_attempt_at == failed_at
    assert updated.last_error == "permanent transport error"
    assert updated.is_available(at=failed_at) is False


def test_mark_failed_rejects_empty_error() -> None:
    message = OutboxMessage.create(event=make_event())

    with pytest.raises(
        ValueError,
        match="error must not be empty",
    ):
        message.mark_failed(error="   ")
