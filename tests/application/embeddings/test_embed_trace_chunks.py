"""Unit tests for the EmbedTraceChunks application use case."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Sequence
from uuid import UUID, uuid4

import pytest

from globalroamer_platform.application.embeddings.embed_trace_chunks import (
    DuplicateTraceChunkError,
    EmbedTraceChunks,
    EmbedTraceChunksCommand,
    EmbeddingCountMismatchError,
    EmbeddingGenerationError,
    InconsistentEmbeddingDimensionsError,
    InconsistentEmbeddingModelError,
    TraceChunkOwnershipError,
    TraceChunksNotFoundError,
)
from globalroamer_platform.application.ports.embedding_provider import (
    EmbeddingBatch,
)
from globalroamer_platform.domain.models.embedding_record import (
    EmbeddingRecord,
)
from globalroamer_platform.domain.models.trace_chunk import (
    TraceChunk,
)


@dataclass
class FakeTraceChunkReader:
    """In-memory trace-chunk reader used by unit tests."""

    chunks: Sequence[TraceChunk]
    calls: list[tuple[str, str]] = field(
        default_factory=list
    )

    async def list_by_trace(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> Sequence[TraceChunk]:
        self.calls.append(
            (
                tenant_id,
                trace_id,
            )
        )

        return self.chunks


@dataclass
class FakeEmbeddingStore:
    """In-memory embedding store used by unit tests."""

    saved_batches: list[
        tuple[EmbeddingRecord, ...]
    ] = field(
        default_factory=list
    )

    async def save_many(
        self,
        records: Sequence[EmbeddingRecord],
    ) -> None:
        self.saved_batches.append(
            tuple(records)
        )

    @property
    def saved_records(
        self,
    ) -> tuple[EmbeddingRecord, ...]:
        return tuple(
            record
            for batch in self.saved_batches
            for record in batch
        )


@dataclass
class DeterministicEmbeddingProvider:
    """Provider returning deterministic vectors for supplied texts."""

    model_name: str = "test-embedding-model"
    model_version: str = "1.0"
    dimensions: int = 3
    calls: list[tuple[str, ...]] = field(
        default_factory=list
    )

    async def embed(
        self,
        texts: Sequence[str],
    ) -> EmbeddingBatch:
        normalized_texts = tuple(texts)
        self.calls.append(
            normalized_texts
        )

        vectors = tuple(
            tuple(
                float(text_index + dimension_index)
                for dimension_index in range(
                    self.dimensions
                )
            )
            for text_index, _ in enumerate(
                normalized_texts,
                start=1,
            )
        )

        return EmbeddingBatch.create(
            model_name=self.model_name,
            model_version=self.model_version,
            vectors=vectors,
        )


@dataclass
class SequencedEmbeddingProvider:
    """Provider returning predefined batches in call order."""

    batches: list[object]
    calls: list[tuple[str, ...]] = field(
        default_factory=list
    )

    async def embed(
        self,
        texts: Sequence[str],
    ) -> object:
        self.calls.append(
            tuple(texts)
        )

        if not self.batches:
            raise AssertionError(
                "provider received more calls than expected"
            )

        return self.batches.pop(0)


def make_chunk(
    *,
    tenant_id: str = "tenant-001",
    trace_id: str = "trace-001",
    testcase_id: str | None = "testcase-001",
    chunk_index: int = 0,
    text: str = "Trace chunk content",
    chunk_id: UUID | None = None,
) -> TraceChunk:
    """Create a valid TraceChunk for application tests."""

    return TraceChunk.create(
        tenant_id=tenant_id,
        trace_id=trace_id,
        testcase_id=testcase_id,
        chunk_index=chunk_index,
        text=text,
        event_ids=(
            uuid4(),
        ),
        event_names=(
            "call_started",
        ),
        event_families=(
            "call",
        ),
        severities=(
            "info",
        ),
        causes=(),
        tags=(
            "test",
        ),
        chunk_id=chunk_id,
    )


def make_use_case(
    *,
    chunks: Sequence[TraceChunk],
    provider: object | None = None,
) -> tuple[
    EmbedTraceChunks,
    FakeTraceChunkReader,
    FakeEmbeddingStore,
    object,
]:
    reader = FakeTraceChunkReader(
        chunks=chunks,
    )
    store = FakeEmbeddingStore()
    selected_provider = (
        provider
        if provider is not None
        else DeterministicEmbeddingProvider()
    )

    use_case = EmbedTraceChunks(
        chunk_reader=reader,
        embedding_store=store,
        embedding_provider=selected_provider,
    )

    return (
        use_case,
        reader,
        store,
        selected_provider,
    )


@pytest.mark.asyncio
async def test_execute_embeds_and_saves_trace_chunks() -> None:
    chunks = (
        make_chunk(
            chunk_index=0,
            text="First trace chunk",
        ),
        make_chunk(
            chunk_index=1,
            text="Second trace chunk",
        ),
    )

    (
        use_case,
        reader,
        store,
        provider,
    ) = make_use_case(
        chunks=chunks,
    )

    result = await use_case.execute(
        EmbedTraceChunksCommand(
            tenant_id="tenant-001",
            trace_id="trace-001",
        )
    )

    assert reader.calls == [
        (
            "tenant-001",
            "trace-001",
        )
    ]

    assert provider.calls == [
        (
            "First trace chunk",
            "Second trace chunk",
        )
    ]

    assert len(store.saved_batches) == 1
    assert len(store.saved_records) == 2

    first_record = store.saved_records[0]
    second_record = store.saved_records[1]

    assert first_record.tenant_id == "tenant-001"
    assert first_record.trace_id == "trace-001"
    assert first_record.testcase_id == "testcase-001"
    assert first_record.chunk_id == chunks[0].id
    assert first_record.model_name == (
        "test-embedding-model"
    )
    assert first_record.model_version == "1.0"
    assert first_record.dimensions == 3
    assert first_record.embedding == (
        1.0,
        2.0,
        3.0,
    )
    assert first_record.content_checksum == hashlib.sha256(
        chunks[0].text.encode("utf-8")
    ).hexdigest()

    assert second_record.chunk_id == chunks[1].id
    assert second_record.embedding == (
        2.0,
        3.0,
        4.0,
    )

    assert result.tenant_id == "tenant-001"
    assert result.trace_id == "trace-001"
    assert result.model_name == "test-embedding-model"
    assert result.model_version == "1.0"
    assert result.dimensions == 3
    assert result.chunk_count == 2
    assert result.embedding_count == 2
    assert result.embedding_ids == (
        first_record.id,
        second_record.id,
    )


@pytest.mark.asyncio
async def test_execute_processes_chunks_in_configured_batches() -> None:
    chunks = tuple(
        make_chunk(
            chunk_index=index,
            text=f"Chunk {index}",
        )
        for index in range(5)
    )

    (
        use_case,
        _,
        store,
        provider,
    ) = make_use_case(
        chunks=chunks,
    )

    result = await use_case.execute(
        EmbedTraceChunksCommand(
            tenant_id="tenant-001",
            trace_id="trace-001",
            batch_size=2,
        )
    )

    assert provider.calls == [
        (
            "Chunk 0",
            "Chunk 1",
        ),
        (
            "Chunk 2",
            "Chunk 3",
        ),
        (
            "Chunk 4",
        ),
    ]

    assert len(store.saved_batches) == 1
    assert len(store.saved_records) == 5
    assert result.chunk_count == 5
    assert result.embedding_count == 5


@pytest.mark.asyncio
async def test_execute_preserves_chunk_order() -> None:
    chunks = (
        make_chunk(
            chunk_index=0,
            text="Alpha",
        ),
        make_chunk(
            chunk_index=1,
            text="Beta",
        ),
        make_chunk(
            chunk_index=2,
            text="Gamma",
        ),
    )

    (
        use_case,
        _,
        store,
        _,
    ) = make_use_case(
        chunks=chunks,
    )

    await use_case.execute(
        EmbedTraceChunksCommand(
            tenant_id="tenant-001",
            trace_id="trace-001",
            batch_size=2,
        )
    )

    assert tuple(
        record.chunk_id
        for record in store.saved_records
    ) == tuple(
        chunk.id
        for chunk in chunks
    )


@pytest.mark.asyncio
async def test_execute_normalizes_command_identifiers() -> None:
    chunk = make_chunk()

    (
        use_case,
        reader,
        _,
        _,
    ) = make_use_case(
        chunks=(
            chunk,
        ),
    )

    result = await use_case.execute(
        EmbedTraceChunksCommand(
            tenant_id="  tenant-001  ",
            trace_id="  trace-001  ",
        )
    )

    assert reader.calls == [
        (
            "tenant-001",
            "trace-001",
        )
    ]
    assert result.tenant_id == "tenant-001"
    assert result.trace_id == "trace-001"


@pytest.mark.asyncio
async def test_execute_raises_when_trace_has_no_chunks() -> None:
    (
        use_case,
        _,
        store,
        provider,
    ) = make_use_case(
        chunks=(),
    )

    with pytest.raises(
        TraceChunksNotFoundError,
        match=(
            "trace chunks were not found: "
            "tenant_id=tenant-001, trace_id=trace-001"
        ),
    ):
        await use_case.execute(
            EmbedTraceChunksCommand(
                tenant_id="tenant-001",
                trace_id="trace-001",
            )
        )

    assert provider.calls == []
    assert store.saved_records == ()


@pytest.mark.asyncio
async def test_execute_raises_when_provider_returns_wrong_count() -> None:
    chunks = (
        make_chunk(
            chunk_index=0,
            text="First",
        ),
        make_chunk(
            chunk_index=1,
            text="Second",
        ),
    )

    provider = SequencedEmbeddingProvider(
        batches=[
            EmbeddingBatch.create(
                model_name="model",
                model_version="1",
                vectors=(
                    (
                        1.0,
                        2.0,
                    ),
                ),
            )
        ]
    )

    (
        use_case,
        _,
        store,
        _,
    ) = make_use_case(
        chunks=chunks,
        provider=provider,
    )

    with pytest.raises(
        EmbeddingCountMismatchError,
        match="expected=2, actual=1",
    ):
        await use_case.execute(
            EmbedTraceChunksCommand(
                tenant_id="tenant-001",
                trace_id="trace-001",
            )
        )

    assert store.saved_records == ()


@pytest.mark.asyncio
async def test_execute_raises_when_provider_returns_wrong_type() -> None:
    provider = SequencedEmbeddingProvider(
        batches=[
            object(),
        ]
    )

    (
        use_case,
        _,
        store,
        _,
    ) = make_use_case(
        chunks=(
            make_chunk(),
        ),
        provider=provider,
    )

    with pytest.raises(
        EmbeddingGenerationError,
        match=(
            "embedding provider must return "
            "EmbeddingBatch"
        ),
    ):
        await use_case.execute(
            EmbedTraceChunksCommand(
                tenant_id="tenant-001",
                trace_id="trace-001",
            )
        )

    assert store.saved_records == ()


@pytest.mark.asyncio
async def test_execute_rejects_model_change_between_batches() -> None:
    provider = SequencedEmbeddingProvider(
        batches=[
            EmbeddingBatch.create(
                model_name="model-a",
                model_version="1",
                vectors=(
                    (
                        1.0,
                        2.0,
                    ),
                ),
            ),
            EmbeddingBatch.create(
                model_name="model-b",
                model_version="1",
                vectors=(
                    (
                        3.0,
                        4.0,
                    ),
                ),
            ),
        ]
    )

    chunks = (
        make_chunk(
            chunk_index=0,
            text="First",
        ),
        make_chunk(
            chunk_index=1,
            text="Second",
        ),
    )

    (
        use_case,
        _,
        store,
        _,
    ) = make_use_case(
        chunks=chunks,
        provider=provider,
    )

    with pytest.raises(
        InconsistentEmbeddingModelError,
        match=(
            "expected=model-a:1, "
            "actual=model-b:1"
        ),
    ):
        await use_case.execute(
            EmbedTraceChunksCommand(
                tenant_id="tenant-001",
                trace_id="trace-001",
                batch_size=1,
            )
        )

    assert store.saved_records == ()


@pytest.mark.asyncio
async def test_execute_rejects_model_version_change_between_batches() -> None:
    provider = SequencedEmbeddingProvider(
        batches=[
            EmbeddingBatch.create(
                model_name="model",
                model_version="1",
                vectors=(
                    (
                        1.0,
                        2.0,
                    ),
                ),
            ),
            EmbeddingBatch.create(
                model_name="model",
                model_version="2",
                vectors=(
                    (
                        3.0,
                        4.0,
                    ),
                ),
            ),
        ]
    )

    chunks = (
        make_chunk(
            chunk_index=0,
            text="First",
        ),
        make_chunk(
            chunk_index=1,
            text="Second",
        ),
    )

    (
        use_case,
        _,
        store,
        _,
    ) = make_use_case(
        chunks=chunks,
        provider=provider,
    )

    with pytest.raises(
        InconsistentEmbeddingModelError,
        match=(
            "expected=model:1, "
            "actual=model:2"
        ),
    ):
        await use_case.execute(
            EmbedTraceChunksCommand(
                tenant_id="tenant-001",
                trace_id="trace-001",
                batch_size=1,
            )
        )

    assert store.saved_records == ()


@pytest.mark.asyncio
async def test_execute_rejects_dimension_change_between_batches() -> None:
    provider = SequencedEmbeddingProvider(
        batches=[
            EmbeddingBatch.create(
                model_name="model",
                model_version="1",
                vectors=(
                    (
                        1.0,
                        2.0,
                    ),
                ),
            ),
            EmbeddingBatch.create(
                model_name="model",
                model_version="1",
                vectors=(
                    (
                        3.0,
                        4.0,
                        5.0,
                    ),
                ),
            ),
        ]
    )

    chunks = (
        make_chunk(
            chunk_index=0,
            text="First",
        ),
        make_chunk(
            chunk_index=1,
            text="Second",
        ),
    )

    (
        use_case,
        _,
        store,
        _,
    ) = make_use_case(
        chunks=chunks,
        provider=provider,
    )

    with pytest.raises(
        InconsistentEmbeddingDimensionsError,
        match="expected=2, actual=3",
    ):
        await use_case.execute(
            EmbedTraceChunksCommand(
                tenant_id="tenant-001",
                trace_id="trace-001",
                batch_size=1,
            )
        )

    assert store.saved_records == ()


@pytest.mark.asyncio
async def test_execute_rejects_chunk_from_another_tenant() -> None:
    chunk = make_chunk(
        tenant_id="other-tenant",
    )

    (
        use_case,
        _,
        store,
        provider,
    ) = make_use_case(
        chunks=(
            chunk,
        ),
    )

    with pytest.raises(
        TraceChunkOwnershipError,
        match="trace chunk ownership mismatch",
    ):
        await use_case.execute(
            EmbedTraceChunksCommand(
                tenant_id="tenant-001",
                trace_id="trace-001",
            )
        )

    assert provider.calls == []
    assert store.saved_records == ()


@pytest.mark.asyncio
async def test_execute_rejects_chunk_from_another_trace() -> None:
    chunk = make_chunk(
        trace_id="other-trace",
    )

    (
        use_case,
        _,
        store,
        provider,
    ) = make_use_case(
        chunks=(
            chunk,
        ),
    )

    with pytest.raises(
        TraceChunkOwnershipError,
        match="trace chunk ownership mismatch",
    ):
        await use_case.execute(
            EmbedTraceChunksCommand(
                tenant_id="tenant-001",
                trace_id="trace-001",
            )
        )

    assert provider.calls == []
    assert store.saved_records == ()


@pytest.mark.asyncio
async def test_execute_rejects_duplicate_chunk_ids() -> None:
    duplicate_id = uuid4()

    first = make_chunk(
        chunk_index=0,
        text="First",
        chunk_id=duplicate_id,
    )
    second = make_chunk(
        chunk_index=1,
        text="Second",
        chunk_id=duplicate_id,
    )

    (
        use_case,
        _,
        store,
        provider,
    ) = make_use_case(
        chunks=(
            first,
            second,
        ),
    )

    with pytest.raises(
        DuplicateTraceChunkError,
        match=str(duplicate_id),
    ):
        await use_case.execute(
            EmbedTraceChunksCommand(
                tenant_id="tenant-001",
                trace_id="trace-001",
            )
        )

    assert provider.calls == []
    assert store.saved_records == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("batch_size", "exception_type", "message"),
    [
        (
            0,
            ValueError,
            "batch_size must be greater than zero",
        ),
        (
            -1,
            ValueError,
            "batch_size must be greater than zero",
        ),
        (
            True,
            TypeError,
            "batch_size must be an integer",
        ),
        (
            1.5,
            TypeError,
            "batch_size must be an integer",
        ),
        (
            "2",
            TypeError,
            "batch_size must be an integer",
        ),
    ],
)
async def test_execute_rejects_invalid_batch_size(
    batch_size: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    (
        use_case,
        reader,
        store,
        provider,
    ) = make_use_case(
        chunks=(
            make_chunk(),
        ),
    )

    with pytest.raises(
        exception_type,
        match=message,
    ):
        await use_case.execute(
            EmbedTraceChunksCommand(
                tenant_id="tenant-001",
                trace_id="trace-001",
                batch_size=batch_size,  # type: ignore[arg-type]
            )
        )

    assert reader.calls == []
    assert provider.calls == []
    assert store.saved_records == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "field_value", "exception_type"),
    [
        (
            "tenant_id",
            "",
            ValueError,
        ),
        (
            "tenant_id",
            "   ",
            ValueError,
        ),
        (
            "tenant_id",
            None,
            TypeError,
        ),
        (
            "trace_id",
            "",
            ValueError,
        ),
        (
            "trace_id",
            "   ",
            ValueError,
        ),
        (
            "trace_id",
            None,
            TypeError,
        ),
    ],
)
async def test_execute_rejects_invalid_command_identifiers(
    field_name: str,
    field_value: object,
    exception_type: type[Exception],
) -> None:
    command_values: dict[str, object] = {
        "tenant_id": "tenant-001",
        "trace_id": "trace-001",
    }
    command_values[field_name] = field_value

    (
        use_case,
        reader,
        store,
        provider,
    ) = make_use_case(
        chunks=(
            make_chunk(),
        ),
    )

    with pytest.raises(
        exception_type,
        match=field_name,
    ):
        await use_case.execute(
            EmbedTraceChunksCommand(
                tenant_id=command_values[
                    "tenant_id"
                ],  # type: ignore[arg-type]
                trace_id=command_values[
                    "trace_id"
                ],  # type: ignore[arg-type]
            )
        )

    assert reader.calls == []
    assert provider.calls == []
    assert store.saved_records == ()
