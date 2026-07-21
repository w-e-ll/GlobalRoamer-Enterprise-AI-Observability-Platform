from __future__ import annotations

from uuid import uuid4

import pytest

from globalroamer_platform.application.traces.chunk_trace import (
    ChunkTrace,
    ChunkTraceCommand,
)
from globalroamer_platform.domain.services.trace_chunker import (
    TraceChunker,
)

# Reuse the domain fixture helper.
from tests.domain.services.test_trace_chunker import (
    make_event,
)


def create_use_case() -> ChunkTrace:
    return ChunkTrace(
        trace_chunker=TraceChunker(
            chunk_size=10_000,
            chunk_overlap=200,
        )
    )


def test_execute_returns_expected_result() -> None:
    event1 = make_event(sequence_number=1)
    event2 = make_event(sequence_number=2)

    command = ChunkTraceCommand(
        tenant_id="tenant-001",
        trace_id="trace-001",
        testcase_id="TC-001",
    )

    use_case = create_use_case()

    result = use_case.execute(
        command=command,
        operational_events=(
            event1,
            event2,
        ),
    )

    assert result.tenant_id == command.tenant_id
    assert result.trace_id == command.trace_id
    assert result.testcase_id == command.testcase_id

    assert result.source_event_count == 2
    assert result.chunk_count == 1

    assert len(result.chunks) == 1

    chunk = result.chunks[0]

    assert chunk.event_ids == (
        event1.id,
        event2.id,
    )


def test_execute_returns_empty_result() -> None:
    command = ChunkTraceCommand(
        tenant_id="tenant-001",
        trace_id="trace-001",
        testcase_id=None,
    )

    result = create_use_case().execute(
        command=command,
        operational_events=(),
    )

    assert result.source_event_count == 0
    assert result.chunk_count == 0
    assert result.chunks == ()


def test_execute_rejects_invalid_command_type() -> None:
    with pytest.raises(
        TypeError,
        match="command must be a ChunkTraceCommand",
    ):
        create_use_case().execute(
            command=object(),  # type: ignore[arg-type]
            operational_events=(),
        )


def test_execute_rejects_non_tuple_events() -> None:
    command = ChunkTraceCommand(
        tenant_id="tenant-001",
        trace_id="trace-001",
    )

    with pytest.raises(
        TypeError,
        match="operational_events must be a tuple",
    ):
        create_use_case().execute(
            command=command,
            operational_events=[
                make_event(),
            ],  # type: ignore[arg-type]
        )


def test_execute_rejects_invalid_event_item() -> None:
    command = ChunkTraceCommand(
        tenant_id="tenant-001",
        trace_id="trace-001",
    )

    with pytest.raises(
        TypeError,
        match="OperationalEvent",
    ):
        create_use_case().execute(
            command=command,
            operational_events=(
                object(),
            ),  # type: ignore[arg-type]
        )


def test_execute_rejects_tenant_mismatch() -> None:
    command = ChunkTraceCommand(
        tenant_id="tenant-A",
        trace_id="trace-001",
        testcase_id="TC-001",
    )

    event = make_event(
        tenant_id="tenant-B",
    )

    with pytest.raises(
        ValueError,
        match="tenant_id",
    ):
        create_use_case().execute(
            command=command,
            operational_events=(event,),
        )


def test_execute_rejects_trace_mismatch() -> None:
    command = ChunkTraceCommand(
        tenant_id="tenant-001",
        trace_id="trace-A",
        testcase_id="TC-001",
    )

    event = make_event(
        trace_id="trace-B",
    )

    with pytest.raises(
        ValueError,
        match="trace_id",
    ):
        create_use_case().execute(
            command=command,
            operational_events=(event,),
        )


def test_execute_rejects_testcase_mismatch() -> None:
    command = ChunkTraceCommand(
        tenant_id="tenant-001",
        trace_id="trace-001",
        testcase_id="AAA",
    )

    event = make_event(
        testcase_id="BBB",
    )

    with pytest.raises(
        ValueError,
        match="testcase_id",
    ):
        create_use_case().execute(
            command=command,
            operational_events=(event,),
        )


@pytest.mark.parametrize(
    "tenant_id",
    [
        "",
        " ",
        " tenant",
        "tenant ",
    ],
)
def test_command_validates_tenant(
    tenant_id: str,
) -> None:
    with pytest.raises(
        (ValueError, TypeError),
    ):
        ChunkTraceCommand(
            tenant_id=tenant_id,
            trace_id="trace",
        )


@pytest.mark.parametrize(
    "trace_id",
    [
        "",
        " ",
        " trace",
        "trace ",
    ],
)
def test_command_validates_trace(
    trace_id: str,
) -> None:
    with pytest.raises(
        (ValueError, TypeError),
    ):
        ChunkTraceCommand(
            tenant_id="tenant",
            trace_id=trace_id,
        )


def test_command_accepts_null_testcase() -> None:
    command = ChunkTraceCommand(
        tenant_id="tenant",
        trace_id="trace",
        testcase_id=None,
    )

    assert command.testcase_id is None


def test_use_case_requires_chunker() -> None:
    with pytest.raises(
        TypeError,
        match="trace_chunker",
    ):
        ChunkTrace(
            trace_chunker=object(),  # type: ignore[arg-type]
        )


def test_execute_multiple_chunks() -> None:
    use_case = ChunkTrace(
        trace_chunker=TraceChunker(
            chunk_size=350,
            chunk_overlap=50,
        )
    )

    events = tuple(
        make_event(
            sequence_number=i,
            normalized_message="X" * 200,
            event_id=uuid4(),
        )
        for i in range(1, 5)
    )

    command = ChunkTraceCommand(
        tenant_id="tenant-001",
        trace_id="trace-001",
        testcase_id="TC-001",
    )

    result = use_case.execute(
        command=command,
        operational_events=events,
    )

    assert result.source_event_count == 4

    assert result.chunk_count >= 2

    assert len(result.chunks) == result.chunk_count

    for index, chunk in enumerate(
        result.chunks
    ):
        assert chunk.chunk_index == index


def test_result_chunk_indexes_are_sequential() -> None:
    use_case = create_use_case()

    command = ChunkTraceCommand(
        tenant_id="tenant-001",
        trace_id="trace-001",
        testcase_id="TC-001",
    )

    events = tuple(
        make_event(sequence_number=i)
        for i in range(1, 6)
    )

    result = use_case.execute(
        command=command,
        operational_events=events,
    )

    indexes = [
        chunk.chunk_index
        for chunk in result.chunks
    ]

    assert indexes == list(
        range(result.chunk_count)
    )
