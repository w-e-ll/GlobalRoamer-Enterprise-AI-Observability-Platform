from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from globalroamer_platform.domain.models.parsed_trace import ParsedTrace


class ParsedTraceRepository(ABC):
    """
    Application port for persisting ParsedTrace aggregates.

    The aggregate is identified by the business key:

        tenant_id + trace_id

    rather than by a persistence-specific database identifier.
    """

    @abstractmethod
    async def save(
        self,
        parsed_trace: ParsedTrace,
    ) -> None:
        """
        Persist or replace a parsed trace.
        """

    @abstractmethod
    async def get_by_trace_id(
        self,
        trace_id: str,
        *,
        tenant_id: str,
    ) -> ParsedTrace | None:
        """
        Return the parsed trace for a tenant and trace identifier.
        """

    @abstractmethod
    async def exists(
        self,
        trace_id: str,
        *,
        tenant_id: str,
    ) -> bool:
        """
        Return whether a parsed trace already exists.
        """

    @abstractmethod
    async def list_by_tenant(
        self,
        tenant_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ParsedTrace]:
        """
        Return parsed traces for a tenant ordered from newest to oldest.
        """

    @abstractmethod
    async def delete(
        self,
        trace_id: str,
        *,
        tenant_id: str,
    ) -> bool:
        """
        Delete a parsed trace.

        Returns True if a record existed and was removed.
        """
