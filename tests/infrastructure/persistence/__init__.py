from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.domain.models.operational_event import (
    OperationalEvent,
)
from globalroamer_platform.infrastructure.models.operational_event import (
    OperationalEventModel,
)
from globalroamer_platform.infrastructure.persistence.operational_event_mapper import (
    OperationalEventMapper,
)


class OperationalEventStore:
    """
    Persistence gateway for normalized OperationalEvent domain objects.

    The store participates in the transaction owned by the caller.
    It never commits or rolls back the SQLAlchemy session.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        if not isinstance(session, AsyncSession):
            raise TypeError(
                "session must be an AsyncSession"
            )

        self._session = session

    async def save(
        self,
        event: OperationalEvent,
    ) -> None:
        """
        Add one operational event to the current transaction.

        The row is not committed until the transaction owner commits
        the SQLAlchemy session.
        """

        if not isinstance(event, OperationalEvent):
            raise TypeError(
                "event must be an OperationalEvent"
            )

        model = OperationalEventMapper.to_model(
            event
        )

        self._session.add(model)

    async def save_many(
        self,
        events: Sequence[OperationalEvent],
    ) -> None:
        """
        Add multiple operational events to the current transaction.

        Empty sequences are accepted and perform no database operation.
        """

        if isinstance(events, (str, bytes)):
            raise TypeError(
                "events must be a sequence of OperationalEvent objects"
            )

        if not isinstance(events, Sequence):
            raise TypeError(
                "events must be a sequence of OperationalEvent objects"
            )

        event_tuple = tuple(events)

        for event in event_tuple:
            if not isinstance(event, OperationalEvent):
                raise TypeError(
                    "all events must be OperationalEvent objects"
                )

        if not event_tuple:
            return

        models = OperationalEventMapper.to_models(
            event_tuple
        )

        self._session.add_all(
            list(models)
        )

    async def get_by_id(
        self,
        event_id: UUID,
    ) -> OperationalEvent | None:
        """Return one operational event by its UUID."""

        if not isinstance(event_id, UUID):
            raise TypeError(
                "event_id must be a UUID"
            )

        statement = select(
            OperationalEventModel
        ).where(
            OperationalEventModel.id == event_id
        )

        result = await self._session.execute(
            statement
        )

        model = result.scalar_one_or_none()

        if model is None:
            return None

        return OperationalEventMapper.to_domain(
            model
        )

    async def list_by_trace(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> tuple[OperationalEvent, ...]:
        """
        Return all normalized events for one tenant trace.

        Events are ordered by sequence number and source line number.
        """

        if not isinstance(tenant_id, str):
            raise TypeError(
                "tenant_id must be a string"
            )

        if not tenant_id.strip():
            raise ValueError(
                "tenant_id must not be empty"
            )

        if not isinstance(trace_id, str):
            raise TypeError(
                "trace_id must be a string"
            )

        if not trace_id.strip():
            raise ValueError(
                "trace_id must not be empty"
            )

        statement = (
            select(OperationalEventModel)
            .where(
                OperationalEventModel.tenant_id
                == tenant_id,
                OperationalEventModel.trace_id
                == trace_id,
            )
            .order_by(
                OperationalEventModel.sequence_number,
                OperationalEventModel.source_line_number,
                OperationalEventModel.id,
            )
        )

        result = await self._session.execute(
            statement
        )

        models = tuple(
            result.scalars().all()
        )

        return OperationalEventMapper.to_domains(
            models
        )
