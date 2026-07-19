import logging
from uuid import UUID

from globalroamer_platform.application.ports.trace_repository import (
    TraceRepository,
)
from globalroamer_platform.domain.entities.trace import Trace


logger = logging.getLogger(__name__)


class TraceNotFoundError(Exception):
    """Raised when a trace cannot be found by its internal UUID."""

    def __init__(self, trace_id: UUID) -> None:
        self.trace_id = trace_id
        super().__init__(f"Trace {trace_id} was not found")


class GetTrace:
    """Application use case for retrieving one trace."""

    def __init__(self, repository: TraceRepository) -> None:
        self._repository = repository

    async def execute(self, trace_id: UUID) -> Trace:
        logger.info(
            "Get trace use case started internal_id=%s",
            trace_id,
        )

        logger.debug(
            "Retrieving trace from repository internal_id=%s",
            trace_id,
        )

        trace = await self._repository.get_by_id(trace_id)

        if trace is None:
            logger.warning(
                "Get trace use case failed because trace was not found "
                "internal_id=%s",
                trace_id,
            )

            raise TraceNotFoundError(trace_id)

        logger.info(
            "Get trace use case completed internal_id=%s "
            "testcase_id=%s status=%s current_stage=%s version=%d",
            trace.id,
            trace.testcase_id,
            trace.status.value,
            trace.current_stage,
            trace.version,
        )

        return trace
