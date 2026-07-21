from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from globalroamer_platform.application.traces.normalize_trace import (
    NormalizeTrace,
    NormalizeTraceCommand,
    NormalizeTraceResult,
)
from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
    OutboxMessageStatus,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_NORMALIZED,
    TRACE_PARSED,
)
from globalroamer_platform.infrastructure.persistence.operational_event_store import (
    OperationalEventStore,
)
from globalroamer_platform.infrastructure.persistence.parsed_trace_store import (
    ParsedTraceStore,
)
from globalroamer_platform.workers.normalizer_worker import (
    NormalizerWorker,
)


class StubOperationalEventStore(OperationalEventStore):
    """
    OperationalEventStore test double satisfying the worker's runtime
    type check without requiring a real AsyncSession.
    """

    def __init__(self) -> None:
        self.save_many = AsyncMock()


class StubNormalizeTrace(NormalizeTrace):
    """
    NormalizeTrace test double satisfying the worker's runtime type check.
    """

    def __init__(self) -> None:
        self.execute = Mock()


class StubParsedTraceStore(ParsedTraceStore):
    """
    ParsedTraceStore test double satisfying the worker's runtime type check.
    """

    def __init__(self) -> None:
        self.get_domain = AsyncMock()


def make_event(
    *,
    event_type: str = TRACE_PARSED,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_type=event_type,
        event_version=1,
        correlation_id="corr-normalizer-001",
        causation_id=uuid4(),
        tenant_id="tenant-001",
        occurred_at=datetime.now(timezone.utc),
        producer="pytest",
        payload={
            "parsed_trace_id": str(uuid4()),
            "trace_id": "trace-001",
            "testcase_id": "TC-001",
            "row_count": 150,
            "evidence_count": 10,
            "signal_count": 4,
            "extracted_value_count": 12,
            "mapped_value_count": 8,
            "warning_count": 1,
            "error_count": 0,
            "is_valid": True,
            "is_complete": True,
        },
    )


def make_result(
    *,
    parsed_trace_id: UUID,
    testcase_id: str | None = "TC-001",
) -> NormalizeTraceResult:
    return NormalizeTraceResult(
        parsed_trace_id=parsed_trace_id,
        tenant_id="tenant-001",
        trace_id="trace-001",
        testcase_id=testcase_id,
        source_evidence_count=10,
        operational_event_count=4,
        failure_event_count=2,
        high_severity_event_count=1,
        retry_recommended_count=1,
        operational_events=(),
    )


def make_worker() -> tuple[
    NormalizerWorker,
    StubNormalizeTrace,
    StubParsedTraceStore,
    StubOperationalEventStore,
    AsyncMock,
]:
    normalize_trace = StubNormalizeTrace()
    parsed_trace_store = StubParsedTraceStore()
    operational_event_store = StubOperationalEventStore()
    outbox_repository = AsyncMock()

    worker = NormalizerWorker(
        normalize_trace=normalize_trace,
        parsed_trace_store=parsed_trace_store,
        operational_event_store=operational_event_store,
        outbox_repository=outbox_repository,
    )

    return (
        worker,
        normalize_trace,
        parsed_trace_store,
        operational_event_store,
        outbox_repository,
    )


@pytest.mark.anyio
async def test_handle_normalizes_persisted_trace() -> None:
    (
        worker,
        normalize_trace,
        parsed_trace_store,
        operational_event_store,
        outbox_repository,
    ) = make_worker()

    incoming = make_event()
    parsed_trace_id = UUID(
        incoming.payload["parsed_trace_id"]
    )

    persisted_parsed_trace = object()

    parsed_trace_store.get_domain.return_value = (
        persisted_parsed_trace
    )

    result = make_result(
        parsed_trace_id=parsed_trace_id,
    )

    normalize_trace.execute.return_value = result

    outgoing = await worker.handle(incoming)

    parsed_trace_store.get_domain.assert_awaited_once_with(
        tenant_id="tenant-001",
        trace_id="trace-001",
    )

    normalize_trace.execute.assert_called_once()

    execute_arguments = (
        normalize_trace.execute.call_args.kwargs
    )

    command = execute_arguments["command"]

    assert isinstance(command, NormalizeTraceCommand)
    assert command.parsed_trace_id == parsed_trace_id
    assert command.tenant_id == "tenant-001"
    assert command.trace_id == "trace-001"
    assert command.testcase_id == "TC-001"

    assert (
        execute_arguments["parsed_trace"]
        is persisted_parsed_trace
    )

    operational_event_store.save_many.assert_awaited_once_with(
        result.operational_events
    )

    assert outgoing.event_type == TRACE_NORMALIZED
    assert outgoing.event_version == 1
    assert outgoing.correlation_id == (
        incoming.correlation_id
    )
    assert outgoing.causation_id == incoming.event_id
    assert outgoing.tenant_id == "tenant-001"
    assert outgoing.producer == NormalizerWorker.PRODUCER

    assert (
        outgoing.payload["parsed_trace_id"]
        == str(parsed_trace_id)
    )
    assert outgoing.payload["trace_id"] == "trace-001"
    assert outgoing.payload["testcase_id"] == "TC-001"
    assert outgoing.payload["source_evidence_count"] == 10
    assert outgoing.payload["operational_event_count"] == 4
    assert outgoing.payload["failure_event_count"] == 2
    assert outgoing.payload["high_severity_event_count"] == 1
    assert outgoing.payload["retry_recommended_count"] == 1

    outbox_repository.add.assert_awaited_once()

    outbox_message = (
        outbox_repository.add.await_args.args[0]
    )

    assert isinstance(outbox_message, OutboxMessage)
    assert (
        outbox_message.status
        == OutboxMessageStatus.PENDING
    )
    assert outbox_message.attempt_count == 0
    assert outbox_message.event == outgoing
    assert outbox_message.event_id == outgoing.event_id
    assert outbox_message.event_type == TRACE_NORMALIZED
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
    (
        worker,
        normalize_trace,
        parsed_trace_store,
        operational_event_store,
        outbox_repository,
    ) = make_worker()

    incoming = make_event(
        event_type="wrong.event",
    )

    with pytest.raises(
        ValueError,
        match="NormalizerWorker supports only",
    ):
        await worker.handle(incoming)

    parsed_trace_store.get_domain.assert_not_awaited()
    normalize_trace.execute.assert_not_called()
    operational_event_store.save_many.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_requires_parsed_trace_id() -> None:
    (
        worker,
        normalize_trace,
        parsed_trace_store,
        operational_event_store,
        outbox_repository,
    ) = make_worker()

    incoming = make_event()
    del incoming.payload["parsed_trace_id"]

    with pytest.raises(
        ValueError,
        match="parsed_trace_id",
    ):
        await worker.handle(incoming)

    parsed_trace_store.get_domain.assert_not_awaited()
    normalize_trace.execute.assert_not_called()
    operational_event_store.save_many.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_rejects_invalid_parsed_trace_id() -> None:
    (
        worker,
        normalize_trace,
        parsed_trace_store,
        operational_event_store,
        outbox_repository,
    ) = make_worker()

    incoming = make_event()
    incoming.payload["parsed_trace_id"] = "not-a-uuid"

    with pytest.raises(
        ValueError,
        match="parsed_trace_id",
    ):
        await worker.handle(incoming)

    parsed_trace_store.get_domain.assert_not_awaited()
    normalize_trace.execute.assert_not_called()
    operational_event_store.save_many.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_requires_trace_id() -> None:
    (
        worker,
        normalize_trace,
        parsed_trace_store,
        operational_event_store,
        outbox_repository,
    ) = make_worker()

    incoming = make_event()
    del incoming.payload["trace_id"]

    with pytest.raises(
        ValueError,
        match="trace_id",
    ):
        await worker.handle(incoming)

    parsed_trace_store.get_domain.assert_not_awaited()
    normalize_trace.execute.assert_not_called()
    operational_event_store.save_many.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_raises_when_parsed_trace_is_missing() -> None:
    (
        worker,
        normalize_trace,
        parsed_trace_store,
        operational_event_store,
        outbox_repository,
    ) = make_worker()

    incoming = make_event()

    parsed_trace_store.get_domain.return_value = None

    with pytest.raises(
        LookupError,
        match="Persisted ParsedTrace was not found",
    ):
        await worker.handle(incoming)

    parsed_trace_store.get_domain.assert_awaited_once_with(
        tenant_id="tenant-001",
        trace_id="trace-001",
    )

    normalize_trace.execute.assert_not_called()
    operational_event_store.save_many.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_accepts_null_testcase_id() -> None:
    (
        worker,
        normalize_trace,
        parsed_trace_store,
        operational_event_store,
        outbox_repository,
    ) = make_worker()

    incoming = make_event()
    incoming.payload["testcase_id"] = None

    parsed_trace_id = UUID(
        incoming.payload["parsed_trace_id"]
    )

    persisted_parsed_trace = object()

    parsed_trace_store.get_domain.return_value = (
        persisted_parsed_trace
    )

    result = make_result(
        parsed_trace_id=parsed_trace_id,
        testcase_id=None,
    )

    normalize_trace.execute.return_value = result

    outgoing = await worker.handle(incoming)

    command = (
        normalize_trace.execute.call_args.kwargs[
            "command"
        ]
    )

    assert command.testcase_id is None
    assert outgoing.payload["testcase_id"] is None

    operational_event_store.save_many.assert_awaited_once_with(
        result.operational_events
    )

    outbox_repository.add.assert_awaited_once()