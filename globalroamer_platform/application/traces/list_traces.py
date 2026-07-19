import logging
from dataclasses import dataclass

from globalroamer_platform.application.ports.trace_repository import (
    TraceRepository,
)
from globalroamer_platform.domain.entities.trace import Trace


logger = logging.getLogger(__name__)


class InvalidTracePaginationError(ValueError):
    """Raised when trace pagination parameters are invalid."""


@dataclass(frozen=True, slots=True)
class ListTracesQuery:
    """Filtering and pagination parameters for listing traces."""

    tenant_id: str |None = None
    limit: int = 100
    offset: int = 0


class ListTraces:
    """Application use case for retrieving traces."""

    MAX_LIMIT = 500

    def __init__(self, repository: TraceRepository) -> None:
        self._repository = repository

    async def execute(self, query: ListTracesQuery) -> list[Trace]:
        tenant_id = self._normalize_tenant_id(query.tenant_id)

        logger.info(
            "List traces use case started tenant_filter=%s "
            "limit=%d offset=%d",
            tenant_id or "-",
            query.limit,
            query.offset,
        )

        if query.limit < 1:
            logger.warning(
                "Invalid trace pagination: limit=%d",
                query.limit,
            )

            raise InvalidTracePaginationError(
                "limit must be greater than or equal to 1"
            )

        if query.limit > self.MAX_LIMIT:
            logger.warning(
                "Invalid trace pagination: limit=%d exceeds maximum=%d",
                query.limit,
                self.MAX_LIMIT,
            )

            raise InvalidTracePaginationError(
                f"limit must not exceed {self.MAX_LIMIT}"
            )

        if query.offset < 0:
            logger.warning(
                "Invalid trace pagination: offset=%d",
                query.offset,
            )

            raise InvalidTracePaginationError(
                "offset must be greater than or equal to 0"
            )

        logger.debug(
            "Retrieving traces from repository"
        )

        traces = await self._repository.list(
            tenant_id=tenant_id,
            limit=query.limit,
            offset=query.offset,
        )

        logger.info(
            "List traces use case completed result_count=%d "
            "tenant_filter=%s limit=%d offset=%d",
            len(traces),
            tenant_id or "-",
            query.limit,
            query.offset,
        )

        return traces

    @staticmethod
    def _normalize_tenant_id(tenant_id: str | None) -> str | None:
        if tenant_id is None:
            return None

        normalized_tenant_id = tenant_id.strip()

        if not normalized_tenant_id:
            return None

        return normalized_tenant_id
