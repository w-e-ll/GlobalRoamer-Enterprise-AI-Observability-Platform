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
    OutboxMessageStatus,
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
from globalroamer_platform.workers.parser_worker import (
    ParserWorker,
)


ARTIFACT_ID = UUID(
    "11111111-1111-1111-1111-111111111111"
)

PARSED_TRACE_ID = UUID(
    "22222222-2222-2222-2222-222222222222"
)


def make_event(
    *,
    event_type: str = TRACE_ARTIFACT_RECEIVED,
    artifact_id: str | None = str(ARTIFACT_ID),
    tenant_id: str = "tenant-001",
) -> EventEnvelope:
    """Create an incoming artifact event for a parser-worker test."""

    payload: dict[str, object] = {
        "trace_id": "trace-001",
        "testcase_id": "TC-001",
    }

    if artifact_id is not None:
        payload["artifact_id"] = artifact_id

    return EventEnvelope(
        event_id=uuid4(),
        event_type=event_type,
        event_version=1,
        correlation_id="corr-001",
        causation_id=None,
        tenant_id=tenant_id,
        occurred_at=datetime.now(
            timezone.utc,
        ),
        producer="pytest",
        payload=payload,
    )


def make_trace_result(
    *,
    testcase_id: str | None = "TC-001",
) -> ProcessTraceResult:
    """Create the trace-processing result wrapped by ProcessArtifact."""

    return ProcessTraceResult(
        parsed_trace_id=PARSED_TRACE_ID,
        tenant_id="tenant-001",
        trace_id="trace-001",
        testcase_id=testcase_id,
        row_count=150,
        evidence_count=10,
        signal_count=4,
        extracted_value_count=12,
        mapped_value_count=8,
        warning_count=1,
        error_count=0,
        is_valid=True,
        is_complete=True,
    )


def make_result(
    *,
    testcase_id: str | None = "TC-001",
) -> ProcessArtifactResult:
    """Create a successful artifact-processing result."""

    return ProcessArtifactResult(
        artifact_id=ARTIFACT_ID,
        artifact_status=ArtifactStatus.PROCESSED,
        trace_result=make_trace_result(
            testcase_id=testcase_id,
        ),
    )


def make_worker(
    *,
    process_artifact: AsyncMock | None = None,
    outbox_repository: AsyncMock | None = None,
) -> tuple[ParserWorker, AsyncMock, AsyncMock]:
    """Create a ParserWorker with mocked application dependencies."""

    concrete_process_artifact = (
        process_artifact or AsyncMock()
    )

    concrete_outbox_repository = (
        outbox_repository or AsyncMock()
    )

    worker = ParserWorker(
        process_artifact=concrete_process_artifact,
        outbox_repository=concrete_outbox_repository,
    )

    return (
        worker,
        concrete_process_artifact,
        concrete_outbox_repository,
    )


@pytest.mark.anyio
async def test_handle_processes_artifact_event() -> None:
    """The worker processes an artifact and writes TRACE_PARSED to outbox."""

    worker, process_artifact, outbox_repository = (
        make_worker()
    )

    process_artifact.execute.return_value = (
        make_result()
    )

    incoming = make_event()

    outgoing = await worker.handle(
        incoming,
    )

    process_artifact.execute.assert_awaited_once()

    command = (
        process_artifact.execute.await_args.args[0]
    )

    assert command.artifact_id == ARTIFACT_ID
    assert command.tenant_id == "tenant-001"

    assert outgoing.event_type == TRACE_PARSED
    assert outgoing.event_version == 1

    assert (
        outgoing.correlation_id
        == incoming.correlation_id
    )
    assert outgoing.causation_id == incoming.event_id
    assert outgoing.tenant_id == "tenant-001"
    assert outgoing.producer == ParserWorker.PRODUCER

    assert (
        outgoing.payload["artifact_id"]
        == str(ARTIFACT_ID)
    )
    assert (
        outgoing.payload["parsed_trace_id"]
        == str(PARSED_TRACE_ID)
    )
    assert outgoing.payload["trace_id"] == "trace-001"
    assert outgoing.payload["testcase_id"] == "TC-001"
    assert outgoing.payload["row_count"] == 150
    assert outgoing.payload["evidence_count"] == 10
    assert outgoing.payload["signal_count"] == 4

    assert (
        outgoing.payload["extracted_value_count"]
        == 12
    )
    assert (
        outgoing.payload["mapped_value_count"]
        == 8
    )

    assert outgoing.payload["warning_count"] == 1
    assert outgoing.payload["error_count"] == 0
    assert outgoing.payload["is_valid"] is True
    assert outgoing.payload["is_complete"] is True

    outbox_repository.add.assert_awaited_once()

    outbox_message = (
        outbox_repository.add.await_args.args[0]
    )

    assert isinstance(
        outbox_message,
        OutboxMessage,
    )

    assert (
        outbox_message.status
        == OutboxMessageStatus.PENDING
    )
    assert outbox_message.attempt_count == 0
    assert outbox_message.event == outgoing
    assert outbox_message.event_id == outgoing.event_id
    assert outbox_message.event_type == TRACE_PARSED
    assert outbox_message.tenant_id == "tenant-001"

    assert (
        outbox_message.correlation_id
        == incoming.correlation_id
    )

    assert outbox_message.published_at is None
    assert outbox_message.last_attempt_at is None
    assert outbox_message.last_error is None


@pytest.mark.anyio
async def test_handle_rejects_wrong_event_type() -> None:
    """The parser worker accepts only TRACE_ARTIFACT_RECEIVED events."""

    worker, process_artifact, outbox_repository = (
        make_worker()
    )

    event = make_event(
        event_type="wrong.event",
    )

    with pytest.raises(
        ValueError,
        match="ParserWorker supports only",
    ):
        await worker.handle(
            event,
        )

    process_artifact.execute.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_requires_artifact_id() -> None:
    """The incoming event must contain an artifact identifier."""

    worker, process_artifact, outbox_repository = (
        make_worker()
    )

    event = make_event(
        artifact_id=None,
    )

    with pytest.raises(
        ValueError,
        match="artifact_id",
    ):
        await worker.handle(
            event,
        )

    process_artifact.execute.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_rejects_empty_artifact_id() -> None:
    """A blank artifact identifier is rejected before processing."""

    worker, process_artifact, outbox_repository = (
        make_worker()
    )

    event = make_event(
        artifact_id="   ",
    )

    with pytest.raises(
        ValueError,
        match="artifact_id",
    ):
        await worker.handle(
            event,
        )

    process_artifact.execute.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_rejects_invalid_artifact_id() -> None:
    """The artifact identifier must be a valid UUID string."""

    worker, process_artifact, outbox_repository = (
        make_worker()
    )

    event = make_event(
        artifact_id="not-a-uuid",
    )

    with pytest.raises(
        ValueError,
        match=(
            "artifact_id.*valid UUID"
        ),
    ):
        await worker.handle(
            event,
        )

    process_artifact.execute.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_uses_event_tenant_in_command() -> None:
    """The artifact-processing command uses the event tenant."""

    worker, process_artifact, outbox_repository = (
        make_worker()
    )

    process_artifact.execute.return_value = (
        make_result()
    )

    event = make_event(
        tenant_id="tenant-001",
    )

    await worker.handle(
        event,
    )

    command = (
        process_artifact.execute.await_args.args[0]
    )

    assert command.artifact_id == ARTIFACT_ID
    assert command.tenant_id == event.tenant_id

    outbox_repository.add.assert_awaited_once()


@pytest.mark.anyio
async def test_handle_accepts_null_testcase() -> None:
    """A nullable testcase identifier is preserved in TRACE_PARSED."""

    worker, process_artifact, outbox_repository = (
        make_worker()
    )

    process_artifact.execute.return_value = (
        make_result(
            testcase_id=None,
        )
    )

    outgoing = await worker.handle(
        make_event(),
    )

    assert outgoing.payload["testcase_id"] is None

    process_artifact.execute.assert_awaited_once()
    outbox_repository.add.assert_awaited_once()


@pytest.mark.anyio
async def test_handle_propagates_application_failure() -> None:
    """ProcessArtifact failures are propagated without creating outbox data."""

    worker, process_artifact, outbox_repository = (
        make_worker()
    )

    process_artifact.execute.side_effect = (
        RuntimeError(
            "artifact processing unavailable",
        )
    )

    with pytest.raises(
        RuntimeError,
        match="artifact processing unavailable",
    ):
        await worker.handle(
            make_event(),
        )

    process_artifact.execute.assert_awaited_once()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_propagates_outbox_failure() -> None:
    """Outbox persistence failures are propagated to the transaction owner."""

    worker, process_artifact, outbox_repository = (
        make_worker()
    )

    process_artifact.execute.return_value = (
        make_result()
    )

    outbox_repository.add.side_effect = (
        RuntimeError(
            "outbox unavailable",
        )
    )

    with pytest.raises(
        RuntimeError,
        match="outbox unavailable",
    ):
        await worker.handle(
            make_event(),
        )

    process_artifact.execute.assert_awaited_once()
    outbox_repository.add.assert_awaited_once()
