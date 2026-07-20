from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from globalroamer_platform.application.traces.process_trace import (
    ProcessTraceResult,
)
from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
    OutboxMessageStatus,
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


def make_event(
    *,
    event_type: str = TRACE_ARTIFACT_RECEIVED,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_type=event_type,
        event_version=1,
        correlation_id="corr-001",
        causation_id=None,
        tenant_id="tenant-001",
        occurred_at=datetime.now(timezone.utc),
        producer="pytest",
        payload={
            "source_path": "sample_trace.csv",
            "trace_id": "trace-001",
            "testcase_id": "TC-001",
        },
    )


def make_result() -> ProcessTraceResult:
    return ProcessTraceResult(
        parsed_trace_id=uuid4(),
        tenant_id="tenant-001",
        trace_id="trace-001",
        testcase_id="TC-001",
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


def make_worker(
    *,
    process_trace: AsyncMock | None = None,
    outbox_repository: AsyncMock | None = None,
) -> tuple[ParserWorker, AsyncMock, AsyncMock]:
    concrete_process_trace = process_trace or AsyncMock()
    concrete_outbox_repository = (
        outbox_repository or AsyncMock()
    )

    worker = ParserWorker(
        process_trace=concrete_process_trace,
        outbox_repository=concrete_outbox_repository,
    )

    return (
        worker,
        concrete_process_trace,
        concrete_outbox_repository,
    )


@pytest.mark.anyio
async def test_handle_processes_trace_event() -> None:
    worker, process_trace, outbox_repository = make_worker()

    process_trace.execute.return_value = make_result()

    incoming = make_event()

    outgoing = await worker.handle(incoming)

    process_trace.execute.assert_awaited_once()

    command = process_trace.execute.await_args.args[0]

    assert command.source_path == Path(
        "sample_trace.csv"
    )
    assert command.tenant_id == "tenant-001"
    assert command.trace_id == "trace-001"
    assert command.testcase_id == "TC-001"

    assert outgoing.event_type == TRACE_PARSED
    assert outgoing.event_version == 1
    assert outgoing.correlation_id == (
        incoming.correlation_id
    )
    assert outgoing.causation_id == incoming.event_id
    assert outgoing.tenant_id == incoming.tenant_id
    assert outgoing.producer == ParserWorker.PRODUCER

    assert outgoing.payload["trace_id"] == "trace-001"
    assert outgoing.payload["testcase_id"] == "TC-001"
    assert outgoing.payload["row_count"] == 150
    assert outgoing.payload["evidence_count"] == 10
    assert outgoing.payload["signal_count"] == 4
    assert (
        outgoing.payload["extracted_value_count"]
        == 12
    )
    assert outgoing.payload["mapped_value_count"] == 8
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
    worker, process_trace, outbox_repository = (
        make_worker()
    )

    event = make_event(
        event_type="wrong.event",
    )

    with pytest.raises(
        ValueError,
        match="ParserWorker supports only",
    ):
        await worker.handle(event)

    process_trace.execute.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_requires_source_path() -> None:
    worker, process_trace, outbox_repository = (
        make_worker()
    )

    event = make_event()

    del event.payload["source_path"]

    with pytest.raises(
        ValueError,
        match="source_path",
    ):
        await worker.handle(event)

    process_trace.execute.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_requires_trace_id() -> None:
    worker, process_trace, outbox_repository = (
        make_worker()
    )

    event = make_event()

    del event.payload["trace_id"]

    with pytest.raises(
        ValueError,
        match="trace_id",
    ):
        await worker.handle(event)

    process_trace.execute.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_accepts_null_testcase() -> None:
    worker, process_trace, outbox_repository = (
        make_worker()
    )

    result = make_result()

    process_trace.execute.return_value = (
        ProcessTraceResult(
            parsed_trace_id=result.parsed_trace_id,
            tenant_id=result.tenant_id,
            trace_id=result.trace_id,
            testcase_id=None,
            row_count=result.row_count,
            evidence_count=result.evidence_count,
            signal_count=result.signal_count,
            extracted_value_count=(
                result.extracted_value_count
            ),
            mapped_value_count=(
                result.mapped_value_count
            ),
            warning_count=result.warning_count,
            error_count=result.error_count,
            is_valid=result.is_valid,
            is_complete=result.is_complete,
        )
    )

    event = make_event()
    event.payload["testcase_id"] = None

    outgoing = await worker.handle(event)

    command = process_trace.execute.await_args.args[0]

    assert command.testcase_id is None
    assert outgoing.payload["testcase_id"] is None

    outbox_repository.add.assert_awaited_once()


@pytest.mark.anyio
async def test_handle_rejects_invalid_testcase() -> None:
    worker, process_trace, outbox_repository = (
        make_worker()
    )

    event = make_event()
    event.payload["testcase_id"] = ""

    with pytest.raises(
        ValueError,
        match="testcase_id",
    ):
        await worker.handle(event)

    process_trace.execute.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_propagates_application_failure() -> None:
    worker, process_trace, outbox_repository = (
        make_worker()
    )

    process_trace.execute.side_effect = RuntimeError(
        "database unavailable"
    )

    with pytest.raises(
        RuntimeError,
        match="database unavailable",
    ):
        await worker.handle(make_event())

    process_trace.execute.assert_awaited_once()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_propagates_outbox_failure() -> None:
    worker, process_trace, outbox_repository = (
        make_worker()
    )

    process_trace.execute.return_value = make_result()

    outbox_repository.add.side_effect = RuntimeError(
        "outbox unavailable"
    )

    with pytest.raises(
        RuntimeError,
        match="outbox unavailable",
    ):
        await worker.handle(make_event())

    process_trace.execute.assert_awaited_once()
    outbox_repository.add.assert_awaited_once()
