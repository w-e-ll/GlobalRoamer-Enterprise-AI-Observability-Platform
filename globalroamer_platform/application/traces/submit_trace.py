"""Application use case for submitting trace artifacts for asynchronous processing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from globalroamer_platform.application.ports.outbox_repository import OutboxRepository
from globalroamer_platform.domain.entities.outbox_message import OutboxMessage
from globalroamer_platform.domain.events.event_envelope import EventEnvelope
from globalroamer_platform.domain.events.event_types import TRACE_ARTIFACT_RECEIVED


@dataclass(frozen=True, slots=True)
class SubmitTraceCommand:
    source_path: Path
    tenant_id: str
    trace_id: str
    testcase_id: str
    correlation_id: str

    def __post_init__(self) -> None:
        source_path = Path(self.source_path)
        tenant_id = self.tenant_id.strip()
        trace_id = self.trace_id.strip()
        testcase_id = self.testcase_id.strip()
        correlation_id = self.correlation_id.strip()

        if not str(source_path).strip():
            raise ValueError("source_path must not be empty")
        if not tenant_id:
            raise ValueError("tenant_id must not be empty")
        if not trace_id:
            raise ValueError("trace_id must not be empty")
        if not testcase_id:
            raise ValueError("testcase_id must not be empty")
        if not correlation_id:
            raise ValueError("correlation_id must not be empty")

        object.__setattr__(self, "source_path", source_path)
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "trace_id", trace_id)
        object.__setattr__(self, "testcase_id", testcase_id)
        object.__setattr__(self, "correlation_id", correlation_id)


@dataclass(frozen=True, slots=True)
class SubmitTraceResult:
    submission_event_id: UUID
    outbox_message_id: UUID
    tenant_id: str
    trace_id: str
    testcase_id: str
    correlation_id: str
    status: str


class SubmitTrace:
    PRODUCER = "globalroamer.trace-submission-api"

    def __init__(self, *, outbox_repository: OutboxRepository) -> None:
        self._outbox_repository = outbox_repository

    async def execute(self, command: SubmitTraceCommand) -> SubmitTraceResult:
        if not isinstance(command, SubmitTraceCommand):
            raise TypeError("command must be a SubmitTraceCommand")

        event = EventEnvelope(
            event_id=uuid4(),
            event_type=TRACE_ARTIFACT_RECEIVED,
            event_version=1,
            correlation_id=command.correlation_id,
            causation_id=None,
            tenant_id=command.tenant_id,
            occurred_at=datetime.now(timezone.utc),
            producer=self.PRODUCER,
            payload={
                "source_path": str(command.source_path),
                "trace_id": command.trace_id,
                "testcase_id": command.testcase_id,
            },
        )

        outbox_message = OutboxMessage.create(event=event)
        await self._outbox_repository.add(outbox_message)

        return SubmitTraceResult(
            submission_event_id=event.event_id,
            outbox_message_id=outbox_message.id,
            tenant_id=command.tenant_id,
            trace_id=command.trace_id,
            testcase_id=command.testcase_id,
            correlation_id=command.correlation_id,
            status="accepted",
        )
