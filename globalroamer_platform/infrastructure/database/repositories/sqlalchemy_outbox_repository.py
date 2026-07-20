"""SQLAlchemy implementation of the transactional outbox repository."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.application.ports.outbox_repository import (
    OutboxRepository,
)
from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
    OutboxMessageStatus,
)
from globalroamer_platform.domain.events.event_envelope import EventEnvelope
from globalroamer_platform.infrastructure.models.outbox_message import (
    OutboxMessageModel,
)


class SQLAlchemyOutboxRepository(OutboxRepository):
    """Persist and retrieve outbox messages using SQLAlchemy."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def add(
        self,
        message: OutboxMessage,
    ) -> None:
        """Add a newly created outbox message to the current transaction."""
        model = self._to_model(message)

        self._session.add(model)
        await self._session.flush()

    async def get_by_id(
        self,
        message_id: UUID,
    ) -> OutboxMessage | None:
        """Return an outbox message by its primary identifier."""
        model = await self._session.get(
            OutboxMessageModel,
            message_id,
        )

        if model is None:
            return None

        return self._to_entity(model)

    async def get_by_event_id(
        self,
        event_id: UUID,
    ) -> OutboxMessage | None:
        """Return an outbox message by its event identifier."""
        statement = select(OutboxMessageModel).where(
            OutboxMessageModel.event_id == event_id,
        )

        result = await self._session.execute(statement)
        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._to_entity(model)

    async def list_available(
        self,
        *,
        available_before: datetime,
        limit: int = 100,
    ) -> list[OutboxMessage]:
        """Return pending messages ready for publication."""
        if limit <= 0:
            raise ValueError("limit must be greater than zero")

        statement = (
            select(OutboxMessageModel)
            .where(
                OutboxMessageModel.status
                == OutboxMessageStatus.PENDING.value,
                OutboxMessageModel.available_at <= available_before,
            )
            .order_by(
                OutboxMessageModel.available_at.asc(),
                OutboxMessageModel.created_at.asc(),
                OutboxMessageModel.id.asc(),
            )
            .limit(limit)
        )

        result = await self._session.execute(statement)
        models = result.scalars().all()

        return [
            self._to_entity(model)
            for model in models
        ]

    async def update(
        self,
        message: OutboxMessage,
    ) -> None:
        """Persist the current state of an existing outbox message."""
        model = await self._session.get(
            OutboxMessageModel,
            message.id,
        )

        if model is None:
            raise LookupError(
                f"Outbox message not found: {message.id}",
            )

        self._update_model(
            model=model,
            message=message,
        )

        await self._session.flush()

    @staticmethod
    def _to_model(
        message: OutboxMessage,
    ) -> OutboxMessageModel:
        """Convert a domain entity into a SQLAlchemy model."""
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

    @staticmethod
    def _to_entity(
        model: OutboxMessageModel,
    ) -> OutboxMessage:
        """Convert a SQLAlchemy model into a domain entity."""
        event = EventEnvelope(
            event_id=model.event_id,
            event_type=model.event_type,
            event_version=model.event_version,
            correlation_id=model.correlation_id,
            causation_id=model.causation_id,
            tenant_id=model.tenant_id,
            occurred_at=model.occurred_at,
            producer=model.producer,
            payload=dict(model.payload),
        )

        return OutboxMessage(
            id=model.id,
            event=event,
            status=OutboxMessageStatus(model.status),
            attempt_count=model.attempt_count,
            created_at=model.created_at,
            available_at=model.available_at,
            published_at=model.published_at,
            last_attempt_at=model.last_attempt_at,
            last_error=model.last_error,
        )

    @staticmethod
    def _update_model(
        *,
        model: OutboxMessageModel,
        message: OutboxMessage,
    ) -> None:
        """Copy mutable lifecycle state to an existing database model."""
        model.status = message.status.value
        model.attempt_count = message.attempt_count
        model.available_at = message.available_at
        model.published_at = message.published_at
        model.last_attempt_at = message.last_attempt_at
        model.last_error = message.last_error
