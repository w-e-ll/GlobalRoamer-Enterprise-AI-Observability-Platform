"""Application read port for persisted trace chunks."""

from __future__ import annotations

from typing import Protocol, Sequence
from uuid import UUID

from globalroamer_platform.domain.models.trace_chunk import (
    TraceChunk,
)


class TraceChunkReader(Protocol):
    """
    Read-side port for persisted trace chunks.

    Infrastructure implementations are responsible for loading domain
    TraceChunk objects from the database in deterministic chunk order.
    """

    async def get_by_id(
        self,
        *,
        chunk_id: UUID,
    ) -> TraceChunk | None:
        """Return one trace chunk by identity."""

        ...

    async def list_by_trace(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> Sequence[TraceChunk]:
        """
        Return all chunks for one tenant trace.

        Results must be ordered by chunk_index ascending.
        """

        ...

    async def list_by_testcase(
        self,
        *,
        tenant_id: str,
        trace_id: str,
        testcase_id: str,
    ) -> Sequence[TraceChunk]:
        """
        Return chunks belonging to one testcase.

        Results must be ordered by chunk_index ascending.
        """

        ...
