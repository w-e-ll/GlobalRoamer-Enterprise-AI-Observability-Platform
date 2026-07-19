from typing import Protocol
from uuid import UUID

from globalroamer_platform.domain.entities.trace import Trace


class TraceRepository(Protocol):
    """Application port for trace persistence operations."""

    async def add(self, trace: Trace) -> Trace:
        """Persist a new trace and return the stored domain entity."""
        ...

    async def get_by_id(self, trace_id: UUID) -> Trace | None:
        """Return a trace by its internal UUID."""
        ...

    async def get_by_external_id(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> Trace | None:
        """Return a trace by the tenant-scoped external trace identifier."""
        ...

    async def list(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Trace]:
        """Return traces using optional tenant filtering and pagination."""
        ...

    async def update(self, trace: Trace) -> Trace:
        """Persist changes to an existing trace."""
        ...
