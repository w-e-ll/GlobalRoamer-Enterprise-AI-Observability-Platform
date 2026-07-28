from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from globalroamer_platform.application.traces.process_artifact import (
    ProcessArtifactResult,
)
from globalroamer_platform.application.traces.process_trace import (
    ProcessTraceResult,
)
from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
)
from globalroamer_platform.domain.entities.source_artifact import (
    ArtifactStatus,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_ARTIFACT_RECEIVED,
    TRACE_PARSED,
)
from globalroamer_platform.infrastructure.messaging.in_memory_event_publisher import (
    InMemoryEventPublisher,
)
from globalroamer_platform.workers.outbox_publisher import (
    OutboxPublisher,
)
from globalroamer_platform.workers.parser_worker import (
    ParserWorker,
)


ARTIFACT_ID = UUID(
    "11111111-1111-1111-1111-111111111111"
)

PARSED_TRACE_ID = UUID(
    "22222222-2222-2222-2222-222222222222"
)


def make_event() -> EventEnvelope:
    """Create an artifact-received event for the parser flow."""

    return EventEnvelope(
        event_id=uuid4(),
        event_type=TRACE_ARTIFACT_RECEIVED,
        event_version=1,
        correlation_id="corr-001",
        causation_id=None,
        tenant_id="tenant-001",
        occurred_at=datetime.now(
            timezone.utc,
        ),
        producer="pytest",
        payload={
            "artifact_id": str(
                ARTIFACT_ID,
            ),
            "trace_id": "trace-001",
            "testcase_id": "TC-001",
        },
    )


def make_trace_result() -> ProcessTraceResult:
    """Create the parsing result returned by ProcessTrace."""

    return ProcessTraceResult(
        parsed_trace_id=PARSED_TRACE_ID,
        tenant_id="tenant-001",
        trace_id="trace-001",
        testcase_id="TC-001",
        row_count=100,
        evidence_count=12,
        signal_count=5,
        extracted_value_count=16,
        mapped_value_count=9,
        warning_count=1,
        error_count=0,
        is_valid=True,
        is_complete=True,
    )


def make_artifact_result() -> ProcessArtifactResult:
    """Create the artifact-processing result used by ParserWorker."""

    return ProcessArtifactResult(
        artifact_id=ARTIFACT_ID,
        artifact_status=ArtifactStatus.PROCESSED,
        trace_result=make_trace_result(),
    )


@pytest.mark.anyio
async def test_parser_event_flow() -> None:
    """
    A parsed artifact event can be published through the outbox adapter.

    The flow exercised here is:

        TRACE_ARTIFACT_RECEIVED
            -> ParserWorker
            -> TRACE_PARSED
            -> OutboxPublisher
            -> InMemoryEventPublisher
    """

    process_artifact = AsyncMock()
    process_artifact.execute.return_value = (
        make_artifact_result()
    )

    outbox_repository = AsyncMock()

    parser_worker = ParserWorker(
        process_artifact=process_artifact,
        outbox_repository=outbox_repository,
    )

    publisher_adapter = InMemoryEventPublisher()

    outbox_publisher = OutboxPublisher(
        event_publisher=publisher_adapter,
    )

    incoming = make_event()

    parsed_event = await parser_worker.handle(
        incoming,
    )

    await outbox_publisher.publish(
        parsed_event,
    )

    assert publisher_adapter.event_count == 1

    published = publisher_adapter.last_event()

    assert published is not None

    assert published.event_type == TRACE_PARSED
    assert published.event_version == 1

    assert (
        published.correlation_id
        == incoming.correlation_id
    )
    assert published.causation_id == incoming.event_id
    assert published.tenant_id == incoming.tenant_id
    assert published.producer == ParserWorker.PRODUCER

    assert (
        published.payload["artifact_id"]
        == str(ARTIFACT_ID)
    )
    assert (
        published.payload["parsed_trace_id"]
        == str(PARSED_TRACE_ID)
    )
    assert published.payload["trace_id"] == "trace-001"
    assert published.payload["testcase_id"] == "TC-001"
    assert published.payload["row_count"] == 100
    assert published.payload["evidence_count"] == 12
    assert published.payload["signal_count"] == 5

    assert (
        published.payload["extracted_value_count"]
        == 16
    )
    assert (
        published.payload["mapped_value_count"]
        == 9
    )

    assert published.payload["warning_count"] == 1
    assert published.payload["error_count"] == 0
    assert published.payload["is_valid"] is True
    assert published.payload["is_complete"] is True

    process_artifact.execute.assert_awaited_once()

    command = (
        process_artifact.execute.await_args.args[0]
    )

    assert command.artifact_id == ARTIFACT_ID
    assert command.tenant_id == "tenant-001"

    outbox_repository.add.assert_awaited_once()

    outbox_message = (
        outbox_repository.add.await_args.args[0]
    )

    assert isinstance(
        outbox_message,
        OutboxMessage,
    )
    assert outbox_message.event == parsed_event
    assert outbox_message.event_id == parsed_event.event_id
    assert outbox_message.event_type == TRACE_PARSED
