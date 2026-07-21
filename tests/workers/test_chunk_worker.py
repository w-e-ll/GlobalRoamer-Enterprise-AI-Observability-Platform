from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from globalroamer_platform.application.ports.outbox_repository import (
    OutboxRepository,
)
from globalroamer_platform.application.traces.chunk_trace import (
    ChunkTrace,
    ChunkTraceResult,
)
from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_CHUNKED,
    TRACE_NORMALIZED,
    TRACE_PARSED,
)
from globalroamer_platform.infrastructure.persistence.operational_event_store import (
    OperationalEventStore,
)
from globalroamer_platform.infrastructure.persistence.trace_chunk_store import (
    TraceChunkStore,
)
from globalroamer_platform.workers.chunk_worker import (
    ChunkWorker,
)
from tests.infrastructure.persistence.test_trace_chunk_mapper import (
    make_chunk,
)


def make_source_event(
    *,
    event_type: str = TRACE_NORMALIZED,
    tenant_id: str | None = None,
    trace_id: str | None = None,
    testcase_id: str | None = None,
    correlation_id: str = "correlation-001",
    payload: dict[str, object] | None = None,
) -> EventEnvelope:
    chunk = make_chunk()

    resolved_tenant_id = (
        tenant_id
        if tenant_id is not None
        else chunk.tenant_id
    )
    resolved_trace_id = (
        trace_id
        if trace_id is not None
        else chunk.trace_id
    )
    resolved_testcase_id = (
        testcase_id
        if testcase_id is not None
        else chunk.testcase_id
    )

    resolved_payload: dict[str, object] = (
        payload
        if payload is not None
        else {
            "trace_id": resolved_trace_id,
            "testcase_id": resolved_testcase_id,
            "operational_event_count": (
                chunk.event_count
            ),
        }
    )

    return EventEnvelope(
        event_id=uuid4(),
        event_type=event_type,
        event_version=1,
        correlation_id=correlation_id,
        causation_id=uuid4(),
        tenant_id=resolved_tenant_id,
        occurred_at=datetime.now(timezone.utc),
        producer="globalroamer.normalizer-worker",
        payload=resolved_payload,
    )


def make_chunk_result() -> ChunkTraceResult:
    chunk = make_chunk()

    return ChunkTraceResult(
        tenant_id=chunk.tenant_id,
        trace_id=chunk.trace_id,
        testcase_id=chunk.testcase_id,
        source_event_count=chunk.event_count,
        chunk_count=1,
        chunks=(chunk,),
    )


def make_dependencies() -> tuple[
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
]:
    chunk_trace = MagicMock(
        spec=ChunkTrace,
    )

    operational_event_store = MagicMock(
        spec=OperationalEventStore,
    )
    operational_event_store.list_by_trace = (
        AsyncMock()
    )

    trace_chunk_store = MagicMock(
        spec=TraceChunkStore,
    )
    trace_chunk_store.delete_by_trace = (
        AsyncMock()
    )
    trace_chunk_store.save_many = AsyncMock()

    outbox_repository = MagicMock(
        spec=OutboxRepository,
    )
    outbox_repository.add = AsyncMock()

    return (
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    )


def make_worker() -> tuple[
    ChunkWorker,
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
]:
    (
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    ) = make_dependencies()

    worker = ChunkWorker(
        chunk_trace=chunk_trace,
        operational_event_store=(
            operational_event_store
        ),
        trace_chunk_store=trace_chunk_store,
        outbox_repository=outbox_repository,
    )

    return (
        worker,
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    )


def test_constructor_accepts_valid_dependencies() -> None:
    (
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    ) = make_dependencies()

    worker = ChunkWorker(
        chunk_trace=chunk_trace,
        operational_event_store=(
            operational_event_store
        ),
        trace_chunk_store=trace_chunk_store,
        outbox_repository=outbox_repository,
    )

    assert worker._chunk_trace is chunk_trace
    assert (
        worker._operational_event_store
        is operational_event_store
    )
    assert (
        worker._trace_chunk_store
        is trace_chunk_store
    )
    assert (
        worker._outbox_repository
        is outbox_repository
    )


@pytest.mark.parametrize(
    (
        "dependency_name",
        "expected_message",
    ),
    [
        (
            "chunk_trace",
            "chunk_trace must be a ChunkTrace",
        ),
        (
            "operational_event_store",
            (
                "operational_event_store must be an "
                "OperationalEventStore"
            ),
        ),
        (
            "trace_chunk_store",
            (
                "trace_chunk_store must be a "
                "TraceChunkStore"
            ),
        ),
    ],
)
def test_constructor_rejects_invalid_dependency(
    dependency_name: str,
    expected_message: str,
) -> None:
    (
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    ) = make_dependencies()

    dependencies: dict[str, object] = {
        "chunk_trace": chunk_trace,
        "operational_event_store": (
            operational_event_store
        ),
        "trace_chunk_store": trace_chunk_store,
        "outbox_repository": outbox_repository,
    }

    dependencies[dependency_name] = object()

    with pytest.raises(
        TypeError,
        match=expected_message,
    ):
        ChunkWorker(
            **dependencies,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_handle_rejects_invalid_event_object() -> None:
    (
        worker,
        _,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    ) = make_worker()

    with pytest.raises(
        TypeError,
        match="event must be an EventEnvelope",
    ):
        await worker.handle(
            object(),  # type: ignore[arg-type]
        )

    (
        operational_event_store
        .list_by_trace
        .assert_not_awaited()
    )
    (
        trace_chunk_store
        .delete_by_trace
        .assert_not_awaited()
    )
    trace_chunk_store.save_many.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_rejects_wrong_event_type() -> None:
    (
        worker,
        _,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    ) = make_worker()

    event = make_source_event(
        event_type=TRACE_PARSED,
    )

    with pytest.raises(
        ValueError,
        match="ChunkWorker supports only",
    ):
        await worker.handle(event)

    (
        operational_event_store
        .list_by_trace
        .assert_not_awaited()
    )
    (
        trace_chunk_store
        .delete_by_trace
        .assert_not_awaited()
    )
    trace_chunk_store.save_many.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"trace_id": None},
        {"trace_id": ""},
        {"trace_id": "   "},
        {"trace_id": 123},
    ],
)
async def test_handle_rejects_invalid_trace_id(
    payload: dict[str, object],
) -> None:
    (
        worker,
        _,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    ) = make_worker()

    event = make_source_event(
        payload=payload,
    )

    with pytest.raises(
        ValueError,
        match="trace_id",
    ):
        await worker.handle(event)

    (
        operational_event_store
        .list_by_trace
        .assert_not_awaited()
    )
    (
        trace_chunk_store
        .delete_by_trace
        .assert_not_awaited()
    )
    trace_chunk_store.save_many.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "testcase_id",
    [
        "",
        "   ",
        123,
        False,
    ],
)
async def test_handle_rejects_invalid_testcase_id(
    testcase_id: object,
) -> None:
    (
        worker,
        _,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    ) = make_worker()

    chunk = make_chunk()

    event = make_source_event(
        payload={
            "trace_id": chunk.trace_id,
            "testcase_id": testcase_id,
        },
    )

    with pytest.raises(
        ValueError,
        match="testcase_id",
    ):
        await worker.handle(event)

    (
        operational_event_store
        .list_by_trace
        .assert_not_awaited()
    )
    (
        trace_chunk_store
        .delete_by_trace
        .assert_not_awaited()
    )
    trace_chunk_store.save_many.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_loads_operational_events() -> None:
    (
        worker,
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    ) = make_worker()

    result = make_chunk_result()
    event = make_source_event(
        tenant_id=result.tenant_id,
        trace_id=result.trace_id,
        testcase_id=result.testcase_id,
    )

    operational_events = ()
    operational_event_store.list_by_trace.return_value = (
        operational_events
    )
    chunk_trace.execute.return_value = result
    trace_chunk_store.delete_by_trace.return_value = 0

    await worker.handle(event)

    (
        operational_event_store
        .list_by_trace
        .assert_awaited_once_with(
            tenant_id=result.tenant_id,
            trace_id=result.trace_id,
        )
    )

    outbox_repository.add.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_executes_chunk_trace_use_case() -> None:
    (
        worker,
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        _,
    ) = make_worker()

    result = make_chunk_result()
    event = make_source_event(
        tenant_id=result.tenant_id,
        trace_id=result.trace_id,
        testcase_id=result.testcase_id,
    )

    operational_events = ()
    operational_event_store.list_by_trace.return_value = (
        operational_events
    )
    chunk_trace.execute.return_value = result
    trace_chunk_store.delete_by_trace.return_value = 0

    await worker.handle(event)

    chunk_trace.execute.assert_called_once()

    call_kwargs = (
        chunk_trace.execute.call_args.kwargs
    )

    command = call_kwargs["command"]

    assert command.tenant_id == result.tenant_id
    assert command.trace_id == result.trace_id
    assert (
        command.testcase_id
        == result.testcase_id
    )
    assert (
        call_kwargs["operational_events"]
        is operational_events
    )


@pytest.mark.asyncio
async def test_handle_deletes_existing_chunks() -> None:
    (
        worker,
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        _,
    ) = make_worker()

    result = make_chunk_result()
    event = make_source_event(
        tenant_id=result.tenant_id,
        trace_id=result.trace_id,
        testcase_id=result.testcase_id,
    )

    operational_event_store.list_by_trace.return_value = ()
    chunk_trace.execute.return_value = result
    trace_chunk_store.delete_by_trace.return_value = 2

    await worker.handle(event)

    (
        trace_chunk_store
        .delete_by_trace
        .assert_awaited_once_with(
            tenant_id=result.tenant_id,
            trace_id=result.trace_id,
        )
    )


@pytest.mark.asyncio
async def test_handle_saves_generated_chunks() -> None:
    (
        worker,
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        _,
    ) = make_worker()

    result = make_chunk_result()
    event = make_source_event(
        tenant_id=result.tenant_id,
        trace_id=result.trace_id,
        testcase_id=result.testcase_id,
    )

    operational_event_store.list_by_trace.return_value = ()
    chunk_trace.execute.return_value = result
    trace_chunk_store.delete_by_trace.return_value = 0

    await worker.handle(event)

    (
        trace_chunk_store
        .save_many
        .assert_awaited_once_with(
            result.chunks
        )
    )


@pytest.mark.asyncio
async def test_handle_returns_trace_chunked_event() -> None:
    (
        worker,
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        _,
    ) = make_worker()

    result = make_chunk_result()
    source_event = make_source_event(
        tenant_id=result.tenant_id,
        trace_id=result.trace_id,
        testcase_id=result.testcase_id,
        correlation_id="correlation-999",
    )

    operational_event_store.list_by_trace.return_value = ()
    chunk_trace.execute.return_value = result
    trace_chunk_store.delete_by_trace.return_value = 0

    outgoing_event = await worker.handle(
        source_event
    )

    assert isinstance(
        outgoing_event,
        EventEnvelope,
    )
    assert outgoing_event.event_type == TRACE_CHUNKED
    assert outgoing_event.event_version == 1
    assert (
        outgoing_event.correlation_id
        == source_event.correlation_id
    )
    assert (
        outgoing_event.causation_id
        == source_event.event_id
    )
    assert (
        outgoing_event.tenant_id
        == result.tenant_id
    )
    assert (
        outgoing_event.producer
        == ChunkWorker.PRODUCER
    )


@pytest.mark.asyncio
async def test_trace_chunked_event_contains_summary_payload() -> None:
    (
        worker,
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        _,
    ) = make_worker()

    result = make_chunk_result()
    source_event = make_source_event(
        tenant_id=result.tenant_id,
        trace_id=result.trace_id,
        testcase_id=result.testcase_id,
    )

    operational_event_store.list_by_trace.return_value = ()
    chunk_trace.execute.return_value = result
    trace_chunk_store.delete_by_trace.return_value = 0

    outgoing_event = await worker.handle(
        source_event
    )

    assert outgoing_event.payload == {
        "trace_id": result.trace_id,
        "testcase_id": result.testcase_id,
        "source_event_count": (
            result.source_event_count
        ),
        "chunk_count": result.chunk_count,
        "chunk_ids": [
            str(chunk.id)
            for chunk in result.chunks
        ],
        "content_hashes": [
            chunk.content_hash
            for chunk in result.chunks
        ],
    }


@pytest.mark.asyncio
async def test_handle_adds_outbox_message() -> None:
    (
        worker,
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    ) = make_worker()

    result = make_chunk_result()
    source_event = make_source_event(
        tenant_id=result.tenant_id,
        trace_id=result.trace_id,
        testcase_id=result.testcase_id,
    )

    operational_event_store.list_by_trace.return_value = ()
    chunk_trace.execute.return_value = result
    trace_chunk_store.delete_by_trace.return_value = 0

    outgoing_event = await worker.handle(
        source_event
    )

    outbox_repository.add.assert_awaited_once()

    outbox_message = (
        outbox_repository.add.call_args.args[0]
    )

    assert isinstance(
        outbox_message,
        OutboxMessage,
    )

    # The exact OutboxMessage storage shape belongs to the domain model.
    # The returned event verifies the outgoing integration-event content.
    assert outgoing_event.event_type == TRACE_CHUNKED


@pytest.mark.asyncio
async def test_handle_supports_null_testcase_id() -> None:
    (
        worker,
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        _,
    ) = make_worker()

    chunk = make_chunk()

    result = ChunkTraceResult(
        tenant_id=chunk.tenant_id,
        trace_id=chunk.trace_id,
        testcase_id=None,
        source_event_count=0,
        chunk_count=0,
        chunks=(),
    )

    source_event = make_source_event(
        tenant_id=result.tenant_id,
        trace_id=result.trace_id,
        payload={
            "trace_id": result.trace_id,
            "testcase_id": None,
        },
    )

    operational_event_store.list_by_trace.return_value = ()
    chunk_trace.execute.return_value = result
    trace_chunk_store.delete_by_trace.return_value = 0

    outgoing_event = await worker.handle(
        source_event
    )

    command = (
        chunk_trace.execute
        .call_args.kwargs["command"]
    )

    assert command.testcase_id is None
    assert (
        outgoing_event.payload["testcase_id"]
        is None
    )


@pytest.mark.asyncio
async def test_handle_propagates_loading_failure() -> None:
    (
        worker,
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    ) = make_worker()

    event = make_source_event()

    operational_event_store.list_by_trace.side_effect = (
        RuntimeError("database unavailable")
    )

    with pytest.raises(
        RuntimeError,
        match="database unavailable",
    ):
        await worker.handle(event)

    chunk_trace.execute.assert_not_called()
    (
        trace_chunk_store
        .delete_by_trace
        .assert_not_awaited()
    )
    trace_chunk_store.save_many.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_propagates_chunking_failure() -> None:
    (
        worker,
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    ) = make_worker()

    event = make_source_event()

    operational_event_store.list_by_trace.return_value = ()
    chunk_trace.execute.side_effect = RuntimeError(
        "chunking failed"
    )

    with pytest.raises(
        RuntimeError,
        match="chunking failed",
    ):
        await worker.handle(event)

    (
        trace_chunk_store
        .delete_by_trace
        .assert_not_awaited()
    )
    trace_chunk_store.save_many.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_propagates_delete_failure() -> None:
    (
        worker,
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    ) = make_worker()

    result = make_chunk_result()
    event = make_source_event(
        tenant_id=result.tenant_id,
        trace_id=result.trace_id,
        testcase_id=result.testcase_id,
    )

    operational_event_store.list_by_trace.return_value = ()
    chunk_trace.execute.return_value = result
    trace_chunk_store.delete_by_trace.side_effect = (
        RuntimeError("delete failed")
    )

    with pytest.raises(
        RuntimeError,
        match="delete failed",
    ):
        await worker.handle(event)

    trace_chunk_store.save_many.assert_not_awaited()
    outbox_repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_propagates_save_failure() -> None:
    (
        worker,
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    ) = make_worker()

    result = make_chunk_result()
    event = make_source_event(
        tenant_id=result.tenant_id,
        trace_id=result.trace_id,
        testcase_id=result.testcase_id,
    )

    operational_event_store.list_by_trace.return_value = ()
    chunk_trace.execute.return_value = result
    trace_chunk_store.delete_by_trace.return_value = 0
    trace_chunk_store.save_many.side_effect = (
        RuntimeError("save failed")
    )

    with pytest.raises(
        RuntimeError,
        match="save failed",
    ):
        await worker.handle(event)

    outbox_repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_propagates_outbox_failure() -> None:
    (
        worker,
        chunk_trace,
        operational_event_store,
        trace_chunk_store,
        outbox_repository,
    ) = make_worker()

    result = make_chunk_result()
    event = make_source_event(
        tenant_id=result.tenant_id,
        trace_id=result.trace_id,
        testcase_id=result.testcase_id,
    )

    operational_event_store.list_by_trace.return_value = ()
    chunk_trace.execute.return_value = result
    trace_chunk_store.delete_by_trace.return_value = 0
    outbox_repository.add.side_effect = RuntimeError(
        "outbox failed"
    )

    with pytest.raises(
        RuntimeError,
        match="outbox failed",
    ):
        await worker.handle(event)

    trace_chunk_store.save_many.assert_awaited_once_with(
        result.chunks
    )
