from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
    OutboxMessageStatus,
)
from globalroamer_platform.domain.events.event_envelope import EventEnvelope
from globalroamer_platform.domain.events.event_types import TRACE_PARSED
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
)
from globalroamer_platform.infrastructure.models.outbox_message import (
    OutboxMessageModel,
)


def make_event(
    *,
    event_id: UUID | None = None,
    correlation_id: str = "corr-001",
    tenant_id: str = "tenant-001",
) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id or uuid4(),
        event_type=TRACE_PARSED,
        event_version=1,
        correlation_id=correlation_id,
        causation_id=uuid4(),
        tenant_id=tenant_id,
        occurred_at=datetime.now(timezone.utc),
        producer="pytest",
        payload={
            "trace_id": "trace-001",
            "testcase_id": "TC-001",
            "row_count": 100,
        },
    )


def make_message(
    *,
    event: EventEnvelope | None = None,
    available_at: datetime | None = None,
) -> OutboxMessage:
    return OutboxMessage.create(
        event=event or make_event(),
        available_at=available_at,
    )


def make_model(
    message: OutboxMessage,
) -> OutboxMessageModel:
    event = message.event

    return OutboxMessageModel(
        id=message.id,
        event_id=event.event_id,
        event_type=event.event_type,
        event_version=event.event_version,
        correlation_id=event.correlation_id,
        causation_id=event.causation_id,
        tenant_id=event.tenant_id,
        occurred_at=event.occurred_at,
        producer=event.producer,
        payload=dict(event.payload),
        status=message.status.value,
        attempt_count=message.attempt_count,
        created_at=message.created_at,
        available_at=message.available_at,
        published_at=message.published_at,
        last_attempt_at=message.last_attempt_at,
        last_error=message.last_error,
    )


def make_session() -> MagicMock:
    session = MagicMock(spec=AsyncSession)

    session.flush = AsyncMock()
    session.get = AsyncMock()
    session.execute = AsyncMock()

    return session


@pytest.mark.anyio
async def test_add_persists_model_and_flushes() -> None:
    session = make_session()
    repository = SQLAlchemyOutboxRepository(session=session)
    message = make_message()

    await repository.add(message)

    session.add.assert_called_once()

    persisted_model = session.add.call_args.args[0]

    assert isinstance(
        persisted_model,
        OutboxMessageModel,
    )
    assert persisted_model.id == message.id
    assert persisted_model.event_id == message.event.event_id
    assert persisted_model.event_type == message.event.event_type
    assert persisted_model.event_version == message.event.event_version
    assert persisted_model.correlation_id == message.event.correlation_id
    assert persisted_model.causation_id == message.event.causation_id
    assert persisted_model.tenant_id == message.event.tenant_id
    assert persisted_model.payload == message.event.payload
    assert persisted_model.status == OutboxMessageStatus.PENDING.value
    assert persisted_model.attempt_count == 0

    session.flush.assert_awaited_once_with()


@pytest.mark.anyio
async def test_get_by_id_returns_domain_entity() -> None:
    session = make_session()
    repository = SQLAlchemyOutboxRepository(session=session)

    message = make_message()
    model = make_model(message)

    session.get.return_value = model

    result = await repository.get_by_id(message.id)

    session.get.assert_awaited_once_with(
        OutboxMessageModel,
        message.id,
    )

    assert result is not None
    assert result.id == message.id
    assert result.event == message.event
    assert result.status == message.status
    assert result.attempt_count == message.attempt_count
    assert result.created_at == message.created_at
    assert result.available_at == message.available_at


@pytest.mark.anyio
async def test_get_by_id_returns_none_when_message_does_not_exist() -> None:
    session = make_session()
    repository = SQLAlchemyOutboxRepository(session=session)

    message_id = uuid4()
    session.get.return_value = None

    result = await repository.get_by_id(message_id)

    assert result is None

    session.get.assert_awaited_once_with(
        OutboxMessageModel,
        message_id,
    )


@pytest.mark.anyio
async def test_get_by_event_id_returns_domain_entity() -> None:
    session = make_session()
    repository = SQLAlchemyOutboxRepository(session=session)

    message = make_message()
    model = make_model(message)

    execution_result = MagicMock()
    execution_result.scalar_one_or_none.return_value = model
    session.execute.return_value = execution_result

    result = await repository.get_by_event_id(
        message.event.event_id,
    )

    assert result is not None
    assert result.id == message.id
    assert result.event.event_id == message.event.event_id
    assert result.event.payload == message.event.payload

    session.execute.assert_awaited_once()


@pytest.mark.anyio
async def test_get_by_event_id_returns_none_when_not_found() -> None:
    session = make_session()
    repository = SQLAlchemyOutboxRepository(session=session)

    execution_result = MagicMock()
    execution_result.scalar_one_or_none.return_value = None
    session.execute.return_value = execution_result

    result = await repository.get_by_event_id(uuid4())

    assert result is None
    session.execute.assert_awaited_once()


@pytest.mark.anyio
async def test_list_available_returns_messages_in_query_result_order() -> None:
    session = make_session()
    repository = SQLAlchemyOutboxRepository(session=session)

    now = datetime.now(timezone.utc)

    first_message = make_message(
        available_at=now - timedelta(minutes=2),
    )
    second_message = make_message(
        available_at=now - timedelta(minutes=1),
    )

    first_model = make_model(first_message)
    second_model = make_model(second_message)

    scalar_result = MagicMock()
    scalar_result.all.return_value = [
        first_model,
        second_model,
    ]

    execution_result = MagicMock()
    execution_result.scalars.return_value = scalar_result
    session.execute.return_value = execution_result

    messages = await repository.list_available(
        available_before=now,
        limit=25,
    )

    assert len(messages) == 2
    assert messages[0].id == first_message.id
    assert messages[1].id == second_message.id

    session.execute.assert_awaited_once()


@pytest.mark.anyio
async def test_list_available_returns_empty_list() -> None:
    session = make_session()
    repository = SQLAlchemyOutboxRepository(session=session)

    scalar_result = MagicMock()
    scalar_result.all.return_value = []

    execution_result = MagicMock()
    execution_result.scalars.return_value = scalar_result
    session.execute.return_value = execution_result

    messages = await repository.list_available(
        available_before=datetime.now(timezone.utc),
    )

    assert messages == []


@pytest.mark.anyio
async def test_list_available_rejects_non_positive_limit() -> None:
    session = make_session()
    repository = SQLAlchemyOutboxRepository(session=session)

    with pytest.raises(
        ValueError,
        match="limit must be greater than zero",
    ):
        await repository.list_available(
            available_before=datetime.now(timezone.utc),
            limit=0,
        )

    session.execute.assert_not_awaited()


@pytest.mark.anyio
async def test_update_persists_message_lifecycle_state() -> None:
    session = make_session()
    repository = SQLAlchemyOutboxRepository(session=session)

    original_message = make_message()
    model = make_model(original_message)

    published_at = datetime.now(timezone.utc)
    updated_message = original_message.mark_published(
        published_at=published_at,
    )

    session.get.return_value = model

    await repository.update(updated_message)

    session.get.assert_awaited_once_with(
        OutboxMessageModel,
        original_message.id,
    )

    assert model.status == OutboxMessageStatus.PUBLISHED.value
    assert model.published_at == published_at
    assert model.last_attempt_at == published_at
    assert model.last_error is None
    assert model.attempt_count == updated_message.attempt_count

    session.flush.assert_awaited_once_with()


@pytest.mark.anyio
async def test_update_persists_failed_message_state() -> None:
    session = make_session()
    repository = SQLAlchemyOutboxRepository(session=session)

    original_message = make_message()
    model = make_model(original_message)

    failed_at = datetime.now(timezone.utc)
    retry_at = failed_at + timedelta(minutes=2)

    failed_message = original_message.mark_failed(
        error="broker unavailable",
        failed_at=failed_at,
        retry_at=retry_at,
    )

    session.get.return_value = model

    await repository.update(failed_message)

    assert model.status == OutboxMessageStatus.PENDING.value
    assert model.attempt_count == 1
    assert model.available_at == retry_at
    assert model.last_attempt_at == failed_at
    assert model.last_error == "broker unavailable"

    session.flush.assert_awaited_once_with()


@pytest.mark.anyio
async def test_update_raises_when_message_does_not_exist() -> None:
    session = make_session()
    repository = SQLAlchemyOutboxRepository(session=session)

    message = make_message()
    session.get.return_value = None

    with pytest.raises(
        LookupError,
        match=f"Outbox message not found: {message.id}",
    ):
        await repository.update(message)

    session.flush.assert_not_awaited()
