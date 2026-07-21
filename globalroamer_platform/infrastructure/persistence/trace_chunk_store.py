from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.domain.models.trace_chunk import (
    TraceChunk,
)
from globalroamer_platform.infrastructure.database.models import (
    TraceChunkModel,
)
from globalroamer_platform.infrastructure.persistence.trace_chunk_mapper import (
    TraceChunkMapper,
)


class TraceChunkStore:
    """
    Persistence gateway for TraceChunk domain objects.

    The caller owns the transaction. This store never commits or rolls back.
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
        chunk: TraceChunk,
    ) -> None:
        """Add one trace chunk to the current transaction."""

        if not isinstance(chunk, TraceChunk):
            raise TypeError(
                "chunk must be a TraceChunk"
            )

        model = TraceChunkMapper.to_model(
            chunk
        )

        self._session.add(model)

    async def save_many(
        self,
        chunks: Sequence[TraceChunk],
    ) -> None:
        """
        Add multiple trace chunks to the current transaction.

        An empty sequence is accepted and performs no operation.
        """

        if isinstance(chunks, (str, bytes)):
            raise TypeError(
                "chunks must be a sequence of TraceChunk objects"
            )

        if not isinstance(chunks, Sequence):
            raise TypeError(
                "chunks must be a sequence of TraceChunk objects"
            )

        chunk_tuple = tuple(chunks)

        for chunk in chunk_tuple:
            if not isinstance(chunk, TraceChunk):
                raise TypeError(
                    "all chunks must be TraceChunk objects"
                )

        if not chunk_tuple:
            return

        models = tuple(
            TraceChunkMapper.to_model(chunk)
            for chunk in chunk_tuple
        )

        self._session.add_all(
            list(models)
        )

    async def get_by_id(
        self,
        chunk_id: UUID,
    ) -> TraceChunk | None:
        """Return a trace chunk by UUID."""

        if not isinstance(chunk_id, UUID):
            raise TypeError(
                "chunk_id must be a UUID"
            )

        statement = select(
            TraceChunkModel
        ).where(
            TraceChunkModel.id == chunk_id
        )

        result = await self._session.execute(
            statement
        )

        model = result.scalar_one_or_none()

        if model is None:
            return None

        return TraceChunkMapper.to_domain(
            model
        )

    async def list_by_trace(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> tuple[TraceChunk, ...]:
        """
        Return all chunks for one tenant trace.

        Results are ordered by chunk index and UUID.
        """

        self._validate_trace_identity(
            tenant_id=tenant_id,
            trace_id=trace_id,
        )

        statement = (
            select(TraceChunkModel)
            .where(
                TraceChunkModel.tenant_id
                == tenant_id,
                TraceChunkModel.trace_id
                == trace_id,
            )
            .order_by(
                TraceChunkModel.chunk_index,
                TraceChunkModel.id,
            )
        )

        result = await self._session.execute(
            statement
        )

        models = tuple(
            result.scalars().all()
        )

        return tuple(
            TraceChunkMapper.to_domain(model)
            for model in models
        )

    async def delete_by_trace(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> int:
        """
        Delete all chunks belonging to one tenant trace.

        Returns the number of deleted database rows. The caller remains
        responsible for committing or rolling back the transaction.
        """

        self._validate_trace_identity(
            tenant_id=tenant_id,
            trace_id=trace_id,
        )

        statement = delete(
            TraceChunkModel
        ).where(
            TraceChunkModel.tenant_id
            == tenant_id,
            TraceChunkModel.trace_id
            == trace_id,
        )

        result = await self._session.execute(
            statement
        )

        return result.rowcount or 0

    @staticmethod
    def _validate_trace_identity(
        *,
        tenant_id: str,
        trace_id: str,
    ) -> None:
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
