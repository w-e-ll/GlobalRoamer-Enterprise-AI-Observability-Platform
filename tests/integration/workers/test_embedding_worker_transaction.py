# tests/integration/workers/test_embedding_worker_transaction.py

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from globalroamer_platform.application.embeddings.embed_trace_chunks import (
    EmbedTraceChunks,
)
from globalroamer_platform.application.ports.embedding_provider import (
    EmbeddingBatch,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    EMBEDDINGS_GENERATED,
    TRACE_CHUNKED,
)
from globalroamer_platform.domain.models.trace_chunk import (
    TraceChunk,
)
from globalroamer_platform.infrastructure.database.models import (
    EmbeddingRecordModel,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
)
from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)
from globalroamer_platform.infrastructure.models.outbox_message import (
    OutboxMessageModel,
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


class DeterministicEmbeddingProvider:
    """
    Deterministic integration-test embedding provider.

    The provider performs no network calls. Every input text receives a
    three-dimensional vector derived from its position in the batch.
    """

    MODEL_NAME = "integration-test-embedding"
    MODEL_VERSION = "1"
    DIMENSIONS = 3

    async def embed(
        self,
        texts: Sequence[str],
    ) -> EmbeddingBatch:
        if not texts:
            raise ValueError(
                "texts must not be empty"
            )

        vectors = tuple(
            (
                float(index + 1),
                float(len(text)),
                float((index + 1) * 10),
            )
            for index, text in enumerate(texts)
        )

        return EmbeddingBatch.create(
            model_name=self.MODEL_NAME,
            model_version=self.MODEL_VERSION,
            vectors=vectors,
        )


def build_trace_chunk(
    *,
    tenant_id: str,
    trace_id: str,
    chunk_index: int,
    text: str,
) -> TraceChunk:
    """Create one valid persisted trace chunk for the integration test."""

    return TraceChunk.create(
        tenant_id=tenant_id,
        trace_id=trace_id,
        testcase_id="TC-EMBEDDING-WORKER-001",
        chunk_index=chunk_index,
        text=text,
        event_ids=(
            uuid4(),
        ),
        event_names=(
            "AUTHENTICATION_FAILURE",
        ),
        event_families=(
            "AUTHENTICATION",
        ),
        severities=(
            "HIGH",
        ),
        causes=(
            "TIMEOUT",
        ),
        tags=(
            "authentication",
            "timeout",
        ),
        has_failure=True,
        has_high_severity=True,
        has_retry_recommended=True,
    )


def build_chunked_event(
    *,
    tenant_id: str,
    trace_id: str,
    chunks: Sequence[TraceChunk],
) -> EventEnvelope:
    """Create the TRACE_CHUNKED event consumed by EmbeddingWorker."""

    return EventEnvelope(
        event_id=uuid4(),
        event_type=TRACE_CHUNKED,
        event_version=1,
        correlation_id=str(uuid4()),
        causation_id=uuid4(),
        tenant_id=tenant_id,
        occurred_at=datetime.now(
            timezone.utc
        ),
        producer="pytest.integration.chunk-worker",
        payload={
            "trace_id": trace_id,
            "testcase_id": (
                "TC-EMBEDDING-WORKER-001"
            ),
            "source_event_count": 2,
            "chunk_count": len(chunks),
            "chunk_ids": [
                str(chunk.id)
                for chunk in chunks
            ],
            "content_hashes": [
                chunk.content_hash
                for chunk in chunks
            ],
            "embedding_batch_size": 1,
        },
    )


def build_embedding_worker(
    *,
    session,
) -> EmbeddingWorker:
    """
    Build the worker with real persistence and a deterministic provider.

    All database dependencies share the same AsyncSession so embedding
    records and the outgoing outbox message participate in one transaction.
    """

    chunk_store = TraceChunkStore(
        session=session,
    )

    embedding_store = EmbeddingRecordStore(
        session=session,
    )

    embedding_provider = (
        DeterministicEmbeddingProvider()
    )

    embed_trace_chunks = EmbedTraceChunks(
        chunk_reader=chunk_store,
        embedding_store=embedding_store,
        embedding_provider=embedding_provider,
    )

    outbox_repository = SQLAlchemyOutboxRepository(
        session=session,
    )

    return EmbeddingWorker(
        embed_trace_chunks=embed_trace_chunks,
        outbox_repository=outbox_repository,
    )


async def persist_trace_chunks(
    *,
    chunks: Sequence[TraceChunk],
) -> None:
    """Persist parent chunk rows before running the embedding transaction."""

    async with async_session_factory() as session:
        chunk_store = TraceChunkStore(
            session=session,
        )

        await chunk_store.save_many(
            tuple(chunks)
        )

        await session.commit()


@pytest.mark.asyncio
async def test_embedding_worker_commits_embeddings_and_outbox_message(
) -> None:
    """
    Embedding records and EMBEDDINGS_GENERATED outbox message are committed.
    """

    tenant_id = (
        f"embedding-worker-{uuid4()}"
    )
    trace_id = (
        f"embedding-trace-{uuid4()}"
    )

    chunks = (
        build_trace_chunk(
            tenant_id=tenant_id,
            trace_id=trace_id,
            chunk_index=0,
            text=(
                "Authentication request failed "
                "because of a timeout."
            ),
        ),
        build_trace_chunk(
            tenant_id=tenant_id,
            trace_id=trace_id,
            chunk_index=1,
            text=(
                "Retry was recommended after "
                "the authentication failure."
            ),
        ),
    )

    await persist_trace_chunks(
        chunks=chunks,
    )

    incoming_event = build_chunked_event(
        tenant_id=tenant_id,
        trace_id=trace_id,
        chunks=chunks,
    )

    async with async_session_factory() as session:
        worker = build_embedding_worker(
            session=session,
        )

        outgoing_event = await worker.handle(
            incoming_event,
        )

        await session.commit()

    assert (
        outgoing_event.event_type
        == EMBEDDINGS_GENERATED
    )
    assert outgoing_event.event_version == 1
    assert outgoing_event.tenant_id == tenant_id
    assert (
        outgoing_event.correlation_id
        == incoming_event.correlation_id
    )
    assert (
        outgoing_event.causation_id
        == incoming_event.event_id
    )
    assert (
        outgoing_event.producer
        == EmbeddingWorker.PRODUCER
    )

    assert (
        outgoing_event.payload["trace_id"]
        == trace_id
    )
    assert (
        outgoing_event.payload["model_name"]
        == DeterministicEmbeddingProvider.MODEL_NAME
    )
    assert (
        outgoing_event.payload["model_version"]
        == DeterministicEmbeddingProvider.MODEL_VERSION
    )
    assert (
        outgoing_event.payload["dimensions"]
        == DeterministicEmbeddingProvider.DIMENSIONS
    )
    assert (
        outgoing_event.payload["chunk_count"]
        == 2
    )
    assert (
        outgoing_event.payload["embedding_count"]
        == 2
    )
    assert (
        len(
            outgoing_event.payload[
                "embedding_ids"
            ]
        )
        == 2
    )

    async with async_session_factory() as session:
        embedding_result = await session.execute(
            select(
                EmbeddingRecordModel
            )
            .where(
                EmbeddingRecordModel.tenant_id
                == tenant_id,
                EmbeddingRecordModel.trace_id
                == trace_id,
            )
            .order_by(
                EmbeddingRecordModel.chunk_id,
                EmbeddingRecordModel.id,
            )
        )

        stored_embeddings = tuple(
            embedding_result.scalars().all()
        )

        outbox_message = await session.scalar(
            select(
                OutboxMessageModel
            ).where(
                OutboxMessageModel.event_id
                == outgoing_event.event_id,
            )
        )

    assert len(stored_embeddings) == 2

    assert {
        record.chunk_id
        for record in stored_embeddings
    } == {
        chunk.id
        for chunk in chunks
    }

    assert all(
        record.tenant_id == tenant_id
        for record in stored_embeddings
    )
    assert all(
        record.trace_id == trace_id
        for record in stored_embeddings
    )
    assert all(
        record.model_name
        == DeterministicEmbeddingProvider.MODEL_NAME
        for record in stored_embeddings
    )
    assert all(
        record.model_version
        == DeterministicEmbeddingProvider.MODEL_VERSION
        for record in stored_embeddings
    )
    assert all(
        record.dimensions
        == DeterministicEmbeddingProvider.DIMENSIONS
        for record in stored_embeddings
    )

    assert outbox_message is not None
    assert (
        outbox_message.event_id
        == outgoing_event.event_id
    )
    assert (
        outbox_message.event_type
        == EMBEDDINGS_GENERATED
    )
    assert (
        outbox_message.tenant_id
        == tenant_id
    )


@pytest.mark.asyncio
async def test_embedding_worker_rolls_back_when_outbox_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Embedding records are rolled back when outbox persistence fails.
    """

    tenant_id = (
        f"embedding-rollback-{uuid4()}"
    )
    trace_id = (
        f"embedding-rollback-trace-{uuid4()}"
    )

    chunks = (
        build_trace_chunk(
            tenant_id=tenant_id,
            trace_id=trace_id,
            chunk_index=0,
            text=(
                "This embedding must be rolled "
                "back with the failed outbox."
            ),
        ),
    )

    await persist_trace_chunks(
        chunks=chunks,
    )

    incoming_event = build_chunked_event(
        tenant_id=tenant_id,
        trace_id=trace_id,
        chunks=chunks,
    )

    async def failing_add(
        self,
        message,
    ) -> None:
        raise RuntimeError(
            "outbox persistence failed"
        )

    monkeypatch.setattr(
        SQLAlchemyOutboxRepository,
        "add",
        failing_add,
    )

    async with async_session_factory() as session:
        worker = build_embedding_worker(
            session=session,
        )

        with pytest.raises(
            RuntimeError,
            match="outbox persistence failed",
        ):
            await worker.handle(
                incoming_event,
            )

        await session.rollback()

    async with async_session_factory() as session:
        embedding_result = await session.execute(
            select(
                EmbeddingRecordModel
            ).where(
                EmbeddingRecordModel.tenant_id
                == tenant_id,
                EmbeddingRecordModel.trace_id
                == trace_id,
            )
        )

        stored_embeddings = tuple(
            embedding_result.scalars().all()
        )

        outbox_message = await session.scalar(
            select(
                OutboxMessageModel
            ).where(
                OutboxMessageModel.tenant_id
                == tenant_id,
                OutboxMessageModel.event_type
                == EMBEDDINGS_GENERATED,
            )
        )

    assert stored_embeddings == ()
    assert outbox_message is None
