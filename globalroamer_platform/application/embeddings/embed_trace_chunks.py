"""Application use case for embedding persisted trace chunks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from globalroamer_platform.application.ports.embedding_provider import (
    EmbeddingBatch,
    EmbeddingProvider,
)
from globalroamer_platform.domain.models.embedding_record import (
    EmbeddingRecord,
)
from globalroamer_platform.domain.models.trace_chunk import (
    TraceChunk,
)
from globalroamer_platform.application.ports.embedding_record_store import (
    EmbeddingRecordStore,
)
from globalroamer_platform.application.ports.trace_chunk_reader import (
    TraceChunkReader,
)


@dataclass(frozen=True, slots=True)
class EmbedTraceChunksCommand:
    """Input command for embedding all chunks belonging to one trace."""

    tenant_id: str
    trace_id: str
    batch_size: int = 32


@dataclass(frozen=True, slots=True)
class EmbedTraceChunksResult:
    """Summary returned after trace chunks have been embedded."""

    tenant_id: str
    trace_id: str
    model_name: str
    model_version: str
    dimensions: int
    chunk_count: int
    embedding_count: int
    embedding_ids: tuple[UUID, ...]


class EmbedTraceChunks:
    """
    Generate and persist embeddings for every chunk belonging to a trace.

    Responsibilities:

    - load trace chunks;
    - preserve their deterministic order;
    - submit chunk content to the embedding provider in batches;
    - validate the provider response;
    - create provider-neutral EmbeddingRecord domain objects;
    - persist all generated records.

    Transaction ownership remains outside this use case. The worker or runtime
    calling this use case is responsible for committing or rolling back.
    """

    def __init__(
            self,
            *,
            chunk_reader: TraceChunkReader,
            embedding_store: EmbeddingRecordStore,
            embedding_provider: EmbeddingProvider,
    ) -> None:
        self._chunk_reader = chunk_reader
        self._embedding_store = embedding_store
        self._embedding_provider = embedding_provider

    async def execute(
        self,
        command: EmbedTraceChunksCommand,
    ) -> EmbedTraceChunksResult:
        """Embed and persist every trace chunk."""

        tenant_id = self._require_non_empty_string(
            command.tenant_id,
            field_name="tenant_id",
        )
        trace_id = self._require_non_empty_string(
            command.trace_id,
            field_name="trace_id",
        )
        batch_size = self._validate_batch_size(
            command.batch_size,
        )

        chunks = tuple(
            await self._chunk_reader.list_by_trace(
                tenant_id=tenant_id,
                trace_id=trace_id,
            )
        )

        if not chunks:
            raise TraceChunksNotFoundError(
                tenant_id=tenant_id,
                trace_id=trace_id,
            )

        self._validate_chunks(
            chunks=chunks,
            tenant_id=tenant_id,
            trace_id=trace_id,
        )

        records: list[EmbeddingRecord] = []
        model_name: str | None = None
        model_version: str | None = None
        dimensions: int | None = None

        for start_index in range(
            0,
            len(chunks),
            batch_size,
        ):
            chunk_batch = chunks[
                start_index : start_index + batch_size
            ]

            provider_batch = await self._embedding_provider.embed(
                tuple(
                    self._chunk_content(chunk)
                    for chunk in chunk_batch
                )
            )

            self._validate_provider_batch(
                provider_batch=provider_batch,
                expected_count=len(chunk_batch),
            )

            if model_name is None:
                model_name = provider_batch.model_name
                model_version = provider_batch.model_version
                dimensions = provider_batch.dimensions
            else:
                self._validate_consistent_model(
                    provider_batch=provider_batch,
                    model_name=model_name,
                    model_version=model_version,
                    dimensions=dimensions,
                )

            records.extend(
                self._build_records(
                    chunks=chunk_batch,
                    provider_batch=provider_batch,
                )
            )

        if not records:
            raise EmbeddingGenerationError(
                "embedding provider returned no records"
            )

        await self._embedding_store.save_many(
            tuple(records),
        )

        # These values are guaranteed to be assigned after at least one
        # successful provider batch.
        assert model_name is not None
        assert model_version is not None
        assert dimensions is not None

        return EmbedTraceChunksResult(
            tenant_id=tenant_id,
            trace_id=trace_id,
            model_name=model_name,
            model_version=model_version,
            dimensions=dimensions,
            chunk_count=len(chunks),
            embedding_count=len(records),
            embedding_ids=tuple(
                record.id
                for record in records
            ),
        )

    @classmethod
    def _build_records(
        cls,
        *,
        chunks: Sequence[TraceChunk],
        provider_batch: EmbeddingBatch,
    ) -> tuple[EmbeddingRecord, ...]:
        records: list[EmbeddingRecord] = []

        for chunk, vector in zip(
            chunks,
            provider_batch.vectors,
            strict=True,
        ):
            content = cls._chunk_content(
                chunk,
            )

            records.append(
                EmbeddingRecord.create(
                    tenant_id=chunk.tenant_id,
                    trace_id=chunk.trace_id,
                    testcase_id=chunk.testcase_id,
                    chunk_id=chunk.id,
                    model_name=provider_batch.model_name,
                    model_version=provider_batch.model_version,
                    embedding=vector,
                    content_checksum=cls._content_checksum(
                        content,
                    ),
                )
            )

        return tuple(records)

    @staticmethod
    def _validate_provider_batch(
        *,
        provider_batch: object,
        expected_count: int,
    ) -> None:
        if not isinstance(
            provider_batch,
            EmbeddingBatch,
        ):
            raise EmbeddingGenerationError(
                "embedding provider must return EmbeddingBatch"
            )

        if provider_batch.count != expected_count:
            raise EmbeddingCountMismatchError(
                expected_count=expected_count,
                actual_count=provider_batch.count,
            )

    @staticmethod
    def _validate_consistent_model(
        *,
        provider_batch: EmbeddingBatch,
        model_name: str,
        model_version: str,
        dimensions: int,
    ) -> None:
        if (
            provider_batch.model_name != model_name
            or provider_batch.model_version != model_version
        ):
            raise InconsistentEmbeddingModelError(
                expected_name=model_name,
                expected_version=model_version,
                actual_name=provider_batch.model_name,
                actual_version=provider_batch.model_version,
            )

        if provider_batch.dimensions != dimensions:
            raise InconsistentEmbeddingDimensionsError(
                expected_dimensions=dimensions,
                actual_dimensions=provider_batch.dimensions,
            )

    @classmethod
    def _validate_chunks(
        cls,
        *,
        chunks: Sequence[TraceChunk],
        tenant_id: str,
        trace_id: str,
    ) -> None:
        seen_chunk_ids: set[UUID] = set()

        for index, chunk in enumerate(chunks):
            if not isinstance(
                chunk,
                TraceChunk,
            ):
                raise TypeError(
                    "chunk reader must return TraceChunk objects: "
                    f"invalid item at index {index}"
                )

            if (
                chunk.tenant_id != tenant_id
                or chunk.trace_id != trace_id
            ):
                raise TraceChunkOwnershipError(
                    chunk_id=chunk.id,
                    expected_tenant_id=tenant_id,
                    expected_trace_id=trace_id,
                    actual_tenant_id=chunk.tenant_id,
                    actual_trace_id=chunk.trace_id,
                )

            if chunk.id in seen_chunk_ids:
                raise DuplicateTraceChunkError(
                    chunk.id,
                )

            seen_chunk_ids.add(
                chunk.id,
            )

            cls._chunk_content(
                chunk,
            )

    @staticmethod
    def _chunk_content(
        chunk: TraceChunk,
    ) -> str:
        content = chunk.text

        if not isinstance(content, str):
            raise TypeError(
                "trace chunk content must be a string"
            )

        if not content.strip():
            raise ValueError(
                f"trace chunk content must not be empty: {chunk.id}"
            )

        return content

    @staticmethod
    def _content_checksum(
        content: str,
    ) -> str:
        return hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _validate_batch_size(
        value: object,
    ) -> int:
        if isinstance(value, bool) or not isinstance(
            value,
            int,
        ):
            raise TypeError(
                "batch_size must be an integer"
            )

        if value <= 0:
            raise ValueError(
                "batch_size must be greater than zero"
            )

        return value

    @staticmethod
    def _require_non_empty_string(
        value: object,
        *,
        field_name: str,
    ) -> str:
        if not isinstance(value, str):
            raise TypeError(
                f"{field_name} must be a string"
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                f"{field_name} must not be empty"
            )

        return normalized


class EmbedTraceChunksError(RuntimeError):
    """Base exception for trace-chunk embedding failures."""


class TraceChunksNotFoundError(EmbedTraceChunksError):
    """Raised when no persisted chunks exist for the requested trace."""

    def __init__(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> None:
        self.tenant_id = tenant_id
        self.trace_id = trace_id

        super().__init__(
            "trace chunks were not found: "
            f"tenant_id={tenant_id}, trace_id={trace_id}"
        )


class EmbeddingGenerationError(EmbedTraceChunksError):
    """Raised when provider output cannot be converted into records."""


class EmbeddingCountMismatchError(EmbeddingGenerationError):
    """Raised when the provider returns the wrong number of vectors."""

    def __init__(
        self,
        *,
        expected_count: int,
        actual_count: int,
    ) -> None:
        self.expected_count = expected_count
        self.actual_count = actual_count

        super().__init__(
            "embedding vector count does not match input text count: "
            f"expected={expected_count}, actual={actual_count}"
        )


class InconsistentEmbeddingModelError(EmbeddingGenerationError):
    """Raised when provider batches report different model identities."""

    def __init__(
        self,
        *,
        expected_name: str,
        expected_version: str,
        actual_name: str,
        actual_version: str,
    ) -> None:
        super().__init__(
            "embedding provider changed model within one operation: "
            f"expected={expected_name}:{expected_version}, "
            f"actual={actual_name}:{actual_version}"
        )


class InconsistentEmbeddingDimensionsError(
    EmbeddingGenerationError
):
    """Raised when provider batches report different vector dimensions."""

    def __init__(
        self,
        *,
        expected_dimensions: int,
        actual_dimensions: int,
    ) -> None:
        super().__init__(
            "embedding provider changed vector dimensions "
            "within one operation: "
            f"expected={expected_dimensions}, "
            f"actual={actual_dimensions}"
        )


class DuplicateTraceChunkError(EmbedTraceChunksError):
    """Raised when the chunk reader returns a duplicate chunk."""

    def __init__(
        self,
        chunk_id: UUID,
    ) -> None:
        self.chunk_id = chunk_id

        super().__init__(
            f"duplicate trace chunk returned by reader: {chunk_id}"
        )


class TraceChunkOwnershipError(EmbedTraceChunksError):
    """Raised when a returned chunk belongs to another tenant or trace."""

    def __init__(
        self,
        *,
        chunk_id: UUID,
        expected_tenant_id: str,
        expected_trace_id: str,
        actual_tenant_id: str,
        actual_trace_id: str,
    ) -> None:
        super().__init__(
            "trace chunk ownership mismatch: "
            f"chunk_id={chunk_id}, "
            f"expected={expected_tenant_id}/{expected_trace_id}, "
            f"actual={actual_tenant_id}/{actual_trace_id}"
        )
