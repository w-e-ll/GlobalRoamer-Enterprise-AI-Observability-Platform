"""Application port for embedding-record persistence."""

from __future__ import annotations

from typing import Protocol, Sequence
from uuid import UUID

from globalroamer_platform.domain.models.embedding_record import (
    EmbeddingRecord,
)


class EmbeddingRecordStore(Protocol):
    """
    Persistence port for embedding records.

    Infrastructure implementations may store embeddings in PostgreSQL,
    pgvector, or another vector-capable database. Transaction ownership
    remains outside the store.
    """

    async def save_many(
        self,
        records: Sequence[EmbeddingRecord],
    ) -> None:
        """
        Persist multiple embedding records.

        Implementations should preserve all-or-nothing transactional behavior
        through the surrounding application transaction.
        """

        ...

    async def get_by_id(
        self,
        *,
        record_id: UUID,
    ) -> EmbeddingRecord | None:
        """Return one embedding record by database identity."""

        ...

    async def list_by_trace(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> Sequence[EmbeddingRecord]:
        """
        Return embedding records belonging to one tenant trace.

        Results should be returned in deterministic chunk order whenever the
        infrastructure layer has access to the related chunk index.
        """

        ...

    async def list_by_chunk(
        self,
        *,
        tenant_id: str,
        chunk_id: UUID,
    ) -> Sequence[EmbeddingRecord]:
        """
        Return all embeddings generated for one trace chunk.

        Multiple records may exist when the same chunk was embedded by
        different model versions.
        """

        ...

    async def get_by_chunk_and_model(
        self,
        *,
        tenant_id: str,
        chunk_id: UUID,
        model_name: str,
        model_version: str,
    ) -> EmbeddingRecord | None:
        """
        Return the embedding for one chunk and exact model identity.

        This method supports idempotent embedding generation and avoids
        recomputing unchanged chunk content with the same model version.
        """

        ...
