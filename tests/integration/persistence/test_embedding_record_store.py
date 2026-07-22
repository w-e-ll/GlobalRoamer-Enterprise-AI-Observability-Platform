from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from globalroamer_platform.domain.models.embedding_record import (
    EmbeddingRecord,
)
from globalroamer_platform.domain.models.trace_chunk import (
    TraceChunk,
)
from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)
from globalroamer_platform.infrastructure.persistence.embedding_record_store import (
    EmbeddingRecordStore,
)
from globalroamer_platform.infrastructure.persistence.trace_chunk_store import (
    TraceChunkStore,
)


def build_trace_chunk(
    *,
    tenant_id: str,
    trace_id: str,
) -> TraceChunk:
    return TraceChunk.create(
        tenant_id=tenant_id,
        trace_id=trace_id,
        testcase_id="TC-EMBEDDING-001",
        chunk_index=0,
        text=(
            "Authentication request failed with timeout. "
            "Retry is recommended."
        ),
        event_ids=(
            uuid4(),
            uuid4(),
        ),
        event_names=(
            "AUTHENTICATION_REQUEST",
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


def build_embedding_record(
    *,
    chunk: TraceChunk,
) -> EmbeddingRecord:
    return EmbeddingRecord(
        id=uuid4(),
        tenant_id=chunk.tenant_id,
        trace_id=chunk.trace_id,
        testcase_id=chunk.testcase_id,
        chunk_id=chunk.id,
        model_name="test-embedding-model",
        model_version="1",
        dimensions=3,
        embedding=(
            0.1,
            0.2,
            0.3,
        ),
        content_checksum=chunk.content_hash,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_save_and_get_by_id_round_trip() -> None:
    tenant_id = f"embedding-store-{uuid4()}"
    trace_id = f"embedding-trace-{uuid4()}"

    chunk = build_trace_chunk(
        tenant_id=tenant_id,
        trace_id=trace_id,
    )
    record = build_embedding_record(
        chunk=chunk,
    )

    async with async_session_factory() as session:
        chunk_store = TraceChunkStore(session)
        embedding_store = EmbeddingRecordStore(session)

        await chunk_store.save(chunk)
        await session.flush()

        await embedding_store.save_many(
            (record,),
        )
        await session.commit()

    async with async_session_factory() as session:
        store = EmbeddingRecordStore(session)

        loaded = await store.get_by_id(
            record.id,
        )

    assert loaded is not None
    assert loaded.id == record.id
    assert loaded.tenant_id == tenant_id
    assert loaded.trace_id == trace_id
    assert loaded.testcase_id == chunk.testcase_id
    assert loaded.chunk_id == chunk.id
    assert loaded.model_name == "test-embedding-model"
    assert loaded.model_version == "1"
    assert loaded.dimensions == 3
    assert loaded.embedding == pytest.approx(
        (
            0.1,
            0.2,
            0.3,
        )
    )
    assert loaded.content_checksum == chunk.content_hash
    assert loaded.created_at == record.created_at


@pytest.mark.asyncio
async def test_list_by_trace_returns_all_embeddings() -> None:
    tenant_id = f"embedding-list-{uuid4()}"
    trace_id = f"embedding-trace-{uuid4()}"

    first_chunk = build_trace_chunk(
        tenant_id=tenant_id,
        trace_id=trace_id,
    )

    second_chunk = TraceChunk.create(
        tenant_id=tenant_id,
        trace_id=trace_id,
        testcase_id="TC-EMBEDDING-001",
        chunk_index=1,
        text="Second trace chunk for embedding persistence.",
        event_ids=(
            uuid4(),
        ),
    )

    first_record = build_embedding_record(
        chunk=first_chunk,
    )
    second_record = build_embedding_record(
        chunk=second_chunk,
    )

    async with async_session_factory() as session:
        chunk_store = TraceChunkStore(session)
        embedding_store = EmbeddingRecordStore(session)

        await chunk_store.save_many(
            (
                first_chunk,
                second_chunk,
            )
        )
        await session.flush()

        await embedding_store.save_many(
            (
                first_record,
                second_record,
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        store = EmbeddingRecordStore(session)

        loaded = await store.list_by_trace(
            tenant_id=tenant_id,
            trace_id=trace_id,
        )

    assert len(loaded) == 2

    assert {
        record.id
        for record in loaded
    } == {
        first_record.id,
        second_record.id,
    }

    assert all(
        record.tenant_id == tenant_id
        for record in loaded
    )

    assert all(
        record.trace_id == trace_id
        for record in loaded
    )


@pytest.mark.asyncio
async def test_get_by_chunk_and_model_returns_matching_record() -> None:
    tenant_id = f"embedding-model-{uuid4()}"
    trace_id = f"embedding-trace-{uuid4()}"

    chunk = build_trace_chunk(
        tenant_id=tenant_id,
        trace_id=trace_id,
    )

    record = build_embedding_record(
        chunk=chunk,
    )

    async with async_session_factory() as session:
        chunk_store = TraceChunkStore(session)
        embedding_store = EmbeddingRecordStore(session)

        await chunk_store.save(chunk)
        await session.flush()

        await embedding_store.save_many(
            (record,),
        )
        await session.commit()

    async with async_session_factory() as session:
        store = EmbeddingRecordStore(session)

        loaded = await store.get_by_chunk_and_model(
            tenant_id=tenant_id,
            chunk_id=chunk.id,
            model_name=record.model_name,
            model_version=record.model_version,
        )

    assert loaded is not None
    assert loaded.id == record.id
    assert loaded.chunk_id == chunk.id
