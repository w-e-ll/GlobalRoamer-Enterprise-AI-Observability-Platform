"""Bootstrap wiring for trace-chunk embedding components.

This module assembles the embedding application use case and worker for one
database session. Transaction ownership remains with the runtime caller.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.application.embeddings.embed_trace_chunks import (
    EmbedTraceChunks,
)
from globalroamer_platform.application.ports.embedding_provider import (
    EmbeddingProvider,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
)
from globalroamer_platform.infrastructure.persistence.embedding_record_store import (
    EmbeddingRecordStore,
)
from globalroamer_platform.infrastructure.persistence.trace_chunk_store import (
    TraceChunkStore,
)
from globalroamer_platform.workers.embedding_worker import (
    EmbeddingWorker,
)


def build_embed_trace_chunks(
    *,
    session: AsyncSession,
    embedding_provider: EmbeddingProvider,
) -> EmbedTraceChunks:
    """
    Build the trace-chunk embedding application use case.

    All persistence adapters share the supplied session so generated
    embedding records participate in the caller-controlled transaction.
    """
    if not isinstance(
        session,
        AsyncSession,
    ):
        raise TypeError(
            "session must be an AsyncSession"
        )

    if not isinstance(
        embedding_provider,
        EmbeddingProvider,
    ):
        raise TypeError(
            "embedding_provider must implement EmbeddingProvider"
        )

    trace_chunk_store = TraceChunkStore(
        session=session,
    )

    embedding_record_store = EmbeddingRecordStore(
        session=session,
    )

    return EmbedTraceChunks(
        chunk_reader=trace_chunk_store,
        embedding_store=embedding_record_store,
        embedding_provider=embedding_provider,
    )


def build_embedding_worker(
    *,
    session: AsyncSession,
    embedding_provider: EmbeddingProvider,
) -> EmbeddingWorker:
    """
    Build an EmbeddingWorker and all session-scoped dependencies.

    The trace chunk reader, embedding record store, and transactional outbox
    repository use the same AsyncSession. The runtime must commit or roll
    back the transaction after invoking the worker.
    """
    embed_trace_chunks = build_embed_trace_chunks(
        session=session,
        embedding_provider=embedding_provider,
    )

    outbox_repository = SQLAlchemyOutboxRepository(
        session=session,
    )

    return EmbeddingWorker(
        embed_trace_chunks=embed_trace_chunks,
        outbox_repository=outbox_repository,
    )
