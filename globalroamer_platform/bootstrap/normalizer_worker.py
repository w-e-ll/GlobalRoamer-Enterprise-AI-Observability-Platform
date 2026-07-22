"""Bootstrap wiring for the chunk worker."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.application.traces.chunk_trace import (
    ChunkTrace,
)
from globalroamer_platform.domain.services.trace_chunker import (
    TraceChunker,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
)
from globalroamer_platform.infrastructure.persistence.operational_event_store import (
    OperationalEventStore,
)
from globalroamer_platform.infrastructure.persistence.trace_chunk_store import (
    TraceChunkStore,
)
from globalroamer_platform.runtime.session_scoped_event_handler import (
    EventHandlerFactory,
)
from globalroamer_platform.workers.chunk_worker import (
    ChunkWorker,
)


def build_chunk_worker(
    *,
    session: AsyncSession,
) -> ChunkWorker:
    """
    Build the complete chunk worker dependency graph.

    The same AsyncSession is shared by:

    - OperationalEventStore
    - TraceChunkStore
    - SQLAlchemyOutboxRepository

    This allows replacement trace chunks and the outgoing transactional
    outbox message to participate in the same transaction owned by the
    outer runtime.
    """

    trace_chunker = TraceChunker()

    chunk_trace = ChunkTrace(
        trace_chunker=trace_chunker,
    )

    operational_event_store = OperationalEventStore(
        session=session,
    )

    trace_chunk_store = TraceChunkStore(
        session=session,
    )

    outbox_repository = SQLAlchemyOutboxRepository(
        session=session,
    )

    return ChunkWorker(
        chunk_trace=chunk_trace,
        operational_event_store=operational_event_store,
        trace_chunk_store=trace_chunk_store,
        outbox_repository=outbox_repository,
    )


def build_chunk_handler_factory() -> EventHandlerFactory:
    """
    Build a session-aware ChunkWorker factory.

    SessionScopedEventHandler invokes the returned factory once per
    dispatched event, supplying the transaction-bound AsyncSession.
    """

    def factory(
        session: AsyncSession,
    ) -> ChunkWorker:
        return build_chunk_worker(
            session=session,
        )

    return factory
