import logging
from dataclasses import dataclass

from globalroamer_platform.application.ports.trace_repository import (
    TraceRepository,
)
from globalroamer_platform.domain.entities.trace import Trace


logger = logging.getLogger(__name__)


class TraceAlreadyExistsError(Exception):
    """Raised when a trace already exists for the same tenant."""

    def __init__(self, *, tenant_id: str, trace_id: str) -> None:
        self.tenant_id = tenant_id
        self.trace_id = trace_id

        super().__init__(
            f"Trace {trace_id!r} already exists for tenant {tenant_id!r}"
        )


@dataclass(frozen=True, slots=True)
class CreateTraceCommand:
    """Input data required to create a trace."""

    tenant_id: str
    trace_id: str
    testcase_id: str


class CreateTrace:
    """Application use case for creating a new trace."""

    def __init__(self, repository: TraceRepository) -> None:
        self._repository = repository

    async def execute(self, command: CreateTraceCommand) -> Trace:
        tenant_id = command.tenant_id.strip()
        trace_id = command.trace_id.strip()
        testcase_id = command.testcase_id.strip()

        logger.info(
            "Create trace use case started testcase_id=%s",
            testcase_id,
        )

        logger.debug(
            "Checking whether trace already exists"
        )

        existing_trace = await self._repository.get_by_external_id(
            tenant_id=tenant_id,
            trace_id=trace_id,
        )

        if existing_trace is not None:
            logger.warning(
                "Trace creation rejected because trace already exists "
                "internal_id=%s testcase_id=%s status=%s",
                existing_trace.id,
                existing_trace.testcase_id,
                existing_trace.status.value,
            )

            raise TraceAlreadyExistsError(
                tenant_id=tenant_id,
                trace_id=trace_id,
            )

        logger.debug(
            "Creating new trace domain entity testcase_id=%s",
            testcase_id,
        )

        trace = Trace.create(
            tenant_id=tenant_id,
            trace_id=trace_id,
            testcase_id=testcase_id,
        )

        logger.debug(
            "Persisting new trace internal_id=%s status=%s "
            "current_stage=%s version=%d",
            trace.id,
            trace.status.value,
            trace.current_stage,
            trace.version,
        )

        persisted_trace = await self._repository.add(trace)

        logger.info(
            "Create trace use case completed internal_id=%s "
            "testcase_id=%s status=%s current_stage=%s version=%d",
            persisted_trace.id,
            persisted_trace.testcase_id,
            persisted_trace.status.value,
            persisted_trace.current_stage,
            persisted_trace.version,
        )

        return persisted_trace
