from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from globalroamer_platform.domain.models.operational_event import (
    OperationalEvent,
    OperationalEventDirection,
    OperationalEventFamily,
    OperationalEventResult,
    OperationalEventSeverity,
)
from globalroamer_platform.domain.models.trace_chunk import (
    TraceChunk,
)
from globalroamer_platform.domain.services.trace_chunker import (
    TraceChunker,
)


def make_event(
    *,
    sequence_number: int = 1,
    tenant_id: str = "tenant-001",
    trace_id: str = "trace-001",
    testcase_id: str | None = "TC-001",
    event_name: str = "LOCATION_UPDATE_FAILED",
    event_family: OperationalEventFamily = (
        OperationalEventFamily.MOBILITY_MANAGEMENT
    ),
    severity: OperationalEventSeverity = (
        OperationalEventSeverity.HIGH
    ),
    result: OperationalEventResult = (
        OperationalEventResult.FAILED
    ),
    raw_message: str = "Location update failed",
    normalized_message: str = (
        "Location update failed for operator A"
    ),
    source_line_number: int | None = None,
    cause: str | None = "PLMN not allowed",
    retry_recommended: bool = True,
    tags: tuple[str, ...] = (
        "mobility",
        "registration",
    ),
    event_id: UUID | None = None,
) -> OperationalEvent:
    return OperationalEvent(
        id=event_id or uuid4(),
        tenant_id=tenant_id,
        trace_id=trace_id,
        testcase_id=testcase_id,
        sequence_number=sequence_number,
        event_name=event_name,
        event_family=event_family,
        severity=severity,
        raw_message=raw_message,
        normalized_message=normalized_message,
        source_line_number=(
            source_line_number
            if source_line_number is not None
            else sequence_number
        ),
        timestamp=datetime(
            2026,
            7,
            21,
            12,
            sequence_number % 60,
            tzinfo=timezone.utc,
        ),
        protocol_layer="NAS",
        direction=OperationalEventDirection.RECEIVE,
        result=result,
        workflow_stage="registration",
        network_domain="mobile",
        operator="Operator A",
        country="Belgium",
        cause=cause,
        retry_recommended=retry_recommended,
        recommendation=(
            "Retry on another network"
            if retry_recommended
            else None
        ),
        tags=tags,
        evidence_lines=(
            raw_message,
        ),
        extracted_values={
            "mcc": "206",
            "mnc": "01",
        },
        metadata={
            "confidence": 0.98,
            "source": "trace",
        },
    )


def test_chunk_returns_empty_tuple_for_empty_input() -> None:
    chunker = TraceChunker()

    result = chunker.chunk(())

    assert result == ()


def test_chunk_creates_one_chunk_for_small_event_set() -> None:
    first = make_event(
        sequence_number=1,
        event_name="LOCATION_UPDATE_REQUEST",
        severity=OperationalEventSeverity.INFO,
        result=OperationalEventResult.OBSERVED,
        cause=None,
        retry_recommended=False,
        tags=("mobility",),
    )
    second = make_event(
        sequence_number=2,
        event_name="LOCATION_UPDATE_FAILED",
    )

    chunker = TraceChunker(
        chunk_size=10_000,
        chunk_overlap=0,
    )

    result = chunker.chunk(
        (
            first,
            second,
        )
    )

    assert len(result) == 1

    chunk = result[0]

    assert isinstance(chunk, TraceChunk)
    assert chunk.tenant_id == "tenant-001"
    assert chunk.trace_id == "trace-001"
    assert chunk.testcase_id == "TC-001"
    assert chunk.chunk_index == 0

    assert chunk.event_ids == (
        first.id,
        second.id,
    )
    assert chunk.event_count == 2

    assert chunk.event_names == (
        "LOCATION_UPDATE_FAILED",
        "LOCATION_UPDATE_REQUEST",
    )

    assert chunk.event_families == (
        "mobility_management",
    )

    assert chunk.severities == (
        "high",
        "info",
    )

    assert chunk.causes == (
        "PLMN not allowed",
    )

    assert chunk.tags == (
        "mobility",
        "registration",
    )

    assert chunk.has_failure is True
    assert chunk.has_high_severity is True
    assert chunk.has_retry_recommended is True

    assert str(first.id) in chunk.text
    assert str(second.id) in chunk.text
    assert "LOCATION_UPDATE_REQUEST" in chunk.text
    assert "LOCATION_UPDATE_FAILED" in chunk.text

    assert chunk.content_hash == (
        TraceChunk.calculate_content_hash(
            chunk.text
        )
    )


def test_chunk_splits_events_when_size_limit_is_exceeded() -> None:
    first = make_event(
        sequence_number=1,
        normalized_message="A" * 150,
        raw_message="first",
    )
    second = make_event(
        sequence_number=2,
        normalized_message="B" * 150,
        raw_message="second",
    )
    third = make_event(
        sequence_number=3,
        normalized_message="C" * 150,
        raw_message="third",
    )

    sizing_chunker = TraceChunker(
        chunk_size=100_000,
        chunk_overlap=0,
    )

    first_size = len(
        sizing_chunker.event_to_text(first)
    )
    second_size = len(
        sizing_chunker.event_to_text(second)
    )

    chunk_size = first_size + second_size

    chunker = TraceChunker(
        chunk_size=chunk_size,
        chunk_overlap=0,
    )

    chunks = chunker.chunk(
        (
            first,
            second,
            third,
        )
    )

    assert len(chunks) >= 2

    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1

    assert chunks[0].event_ids[0] == first.id

    all_event_ids = {
        event_id
        for chunk in chunks
        for event_id in chunk.event_ids
    }

    assert all_event_ids == {
        first.id,
        second.id,
        third.id,
    }


def test_chunk_preserves_complete_event_when_event_exceeds_limit() -> None:
    event = make_event(
        sequence_number=1,
        normalized_message="X" * 5_000,
    )

    chunker = TraceChunker(
        chunk_size=100,
        chunk_overlap=0,
    )

    chunks = chunker.chunk((event,))

    assert len(chunks) == 1
    assert chunks[0].event_ids == (
        event.id,
    )
    assert chunks[0].character_count > 100


def test_chunk_applies_overlap_using_complete_events() -> None:
    first = make_event(
        sequence_number=1,
        normalized_message="first message",
        raw_message="first raw",
    )
    second = make_event(
        sequence_number=2,
        normalized_message="second message",
        raw_message="second raw",
    )
    third = make_event(
        sequence_number=3,
        normalized_message="third message",
        raw_message="third raw",
    )

    sizing_chunker = TraceChunker(
        chunk_size=100_000,
        chunk_overlap=0,
    )

    first_line = sizing_chunker.event_to_text(first)
    second_line = sizing_chunker.event_to_text(second)
    third_line = sizing_chunker.event_to_text(third)

    chunk_size = (
        len(first_line)
        + 1
        + len(second_line)
    )

    overlap_size = len(second_line)

    chunker = TraceChunker(
        chunk_size=chunk_size,
        chunk_overlap=overlap_size,
    )

    chunks = chunker.chunk(
        (
            first,
            second,
            third,
        )
    )

    assert len(chunks) >= 2

    assert first.id in chunks[0].event_ids
    assert second.id in chunks[0].event_ids

    assert second.id in chunks[1].event_ids
    assert third.id in chunks[1].event_ids

    assert second_line in chunks[0].text
    assert second_line in chunks[1].text
    assert third_line in chunks[1].text


def test_chunk_orders_events_by_sequence_number() -> None:
    first = make_event(
        sequence_number=1,
        event_name="FIRST_EVENT",
    )
    second = make_event(
        sequence_number=2,
        event_name="SECOND_EVENT",
    )
    third = make_event(
        sequence_number=3,
        event_name="THIRD_EVENT",
    )

    chunker = TraceChunker(
        chunk_size=100_000,
        chunk_overlap=0,
    )

    chunks = chunker.chunk(
        (
            third,
            first,
            second,
        )
    )

    assert len(chunks) == 1

    assert chunks[0].event_ids == (
        first.id,
        second.id,
        third.id,
    )

    first_position = chunks[0].text.index(
        "FIRST_EVENT"
    )
    second_position = chunks[0].text.index(
        "SECOND_EVENT"
    )
    third_position = chunks[0].text.index(
        "THIRD_EVENT"
    )

    assert first_position < second_position
    assert second_position < third_position


def test_chunk_aggregates_metadata_and_flags() -> None:
    successful = make_event(
        sequence_number=1,
        event_name="AUTHENTICATION_SUCCESS",
        event_family=(
            OperationalEventFamily.AUTHENTICATION
        ),
        severity=OperationalEventSeverity.INFO,
        result=OperationalEventResult.SUCCESS,
        cause=None,
        retry_recommended=False,
        tags=(
            "authentication",
            "success",
        ),
    )

    failed = make_event(
        sequence_number=2,
        event_name="NETWORK_TIMEOUT",
        event_family=(
            OperationalEventFamily.CONNECTIVITY
        ),
        severity=OperationalEventSeverity.CRITICAL,
        result=OperationalEventResult.TIMEOUT,
        cause="Network timeout",
        retry_recommended=True,
        tags=(
            "connectivity",
            "retry",
            "authentication",
        ),
    )

    chunker = TraceChunker(
        chunk_size=100_000,
        chunk_overlap=0,
    )

    chunks = chunker.chunk(
        (
            successful,
            failed,
        )
    )

    assert len(chunks) == 1

    chunk = chunks[0]

    assert chunk.event_names == (
        "AUTHENTICATION_SUCCESS",
        "NETWORK_TIMEOUT",
    )

    assert chunk.event_families == (
        "authentication",
        "connectivity",
    )

    assert chunk.severities == (
        "critical",
        "info",
    )

    assert chunk.causes == (
        "Network timeout",
    )

    assert chunk.tags == (
        "authentication",
        "connectivity",
        "retry",
        "success",
    )

    assert chunk.has_failure is True
    assert chunk.has_high_severity is True
    assert chunk.has_retry_recommended is True


def test_event_to_text_is_deterministic() -> None:
    event = make_event()

    chunker = TraceChunker()

    first = chunker.event_to_text(event)
    second = chunker.event_to_text(event)

    assert first == second

    assert f"event_id={event.id}" in first
    assert "sequence_number=1" in first
    assert "event_family=mobility_management" in first
    assert "severity=high" in first
    assert "result=failed" in first
    assert "retry_recommended=true" in first
    assert "message=Location update failed" in first
    assert "tags=[mobility, registration]" in first


def test_chunk_rejects_non_tuple_collection() -> None:
    chunker = TraceChunker()

    with pytest.raises(
        TypeError,
        match="operational_events must be a tuple",
    ):
        chunker.chunk(
            [
                make_event(),
            ]  # type: ignore[arg-type]
        )


def test_chunk_rejects_invalid_event_item() -> None:
    chunker = TraceChunker()

    with pytest.raises(
        TypeError,
        match=(
            "every operational_events item must "
            "be an OperationalEvent"
        ),
    ):
        chunker.chunk(
            (
                object(),
            )  # type: ignore[arg-type]
        )


def test_chunk_rejects_different_tenant_ids() -> None:
    first = make_event(
        sequence_number=1,
        tenant_id="tenant-001",
    )
    second = make_event(
        sequence_number=2,
        tenant_id="tenant-002",
    )

    chunker = TraceChunker()

    with pytest.raises(
        ValueError,
        match="same tenant_id",
    ):
        chunker.chunk(
            (
                first,
                second,
            )
        )


def test_chunk_rejects_different_trace_ids() -> None:
    first = make_event(
        sequence_number=1,
        trace_id="trace-001",
    )
    second = make_event(
        sequence_number=2,
        trace_id="trace-002",
    )

    chunker = TraceChunker()

    with pytest.raises(
        ValueError,
        match="same trace_id",
    ):
        chunker.chunk(
            (
                first,
                second,
            )
        )


def test_chunk_rejects_different_testcase_ids() -> None:
    first = make_event(
        sequence_number=1,
        testcase_id="TC-001",
    )
    second = make_event(
        sequence_number=2,
        testcase_id="TC-002",
    )

    chunker = TraceChunker()

    with pytest.raises(
        ValueError,
        match="same testcase_id",
    ):
        chunker.chunk(
            (
                first,
                second,
            )
        )


def test_chunk_accepts_null_testcase_id() -> None:
    first = make_event(
        sequence_number=1,
        testcase_id=None,
    )
    second = make_event(
        sequence_number=2,
        testcase_id=None,
    )

    chunker = TraceChunker(
        chunk_size=100_000,
        chunk_overlap=0,
    )

    chunks = chunker.chunk(
        (
            first,
            second,
        )
    )

    assert len(chunks) == 1
    assert chunks[0].testcase_id is None


def test_chunk_rejects_duplicate_event_ids() -> None:
    duplicated_id = uuid4()

    first = make_event(
        sequence_number=1,
        event_id=duplicated_id,
    )
    second = make_event(
        sequence_number=2,
        event_id=duplicated_id,
    )

    chunker = TraceChunker()

    with pytest.raises(
        ValueError,
        match="unique IDs",
    ):
        chunker.chunk(
            (
                first,
                second,
            )
        )


@pytest.mark.parametrize(
    (
        "chunk_size",
        "chunk_overlap",
        "exception_type",
        "message",
    ),
    [
        (
            0,
            0,
            ValueError,
            "chunk_size must be greater than zero",
        ),
        (
            -1,
            0,
            ValueError,
            "chunk_size must be greater than zero",
        ),
        (
            100,
            -1,
            ValueError,
            "chunk_overlap must be greater than or equal to zero",
        ),
        (
            100,
            100,
            ValueError,
            "chunk_overlap must be smaller than chunk_size",
        ),
        (
            100,
            101,
            ValueError,
            "chunk_overlap must be smaller than chunk_size",
        ),
    ],
)
def test_invalid_configuration_is_rejected(
    chunk_size: int,
    chunk_overlap: int,
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(
        exception_type,
        match=message,
    ):
        TraceChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )


@pytest.mark.parametrize(
    (
        "chunk_size",
        "chunk_overlap",
        "message",
    ),
    [
        (
            True,
            0,
            "chunk_size must be an integer",
        ),
        (
            100.5,
            0,
            "chunk_size must be an integer",
        ),
        (
            100,
            True,
            "chunk_overlap must be an integer",
        ),
        (
            100,
            10.5,
            "chunk_overlap must be an integer",
        ),
    ],
)
def test_invalid_configuration_types_are_rejected(
    chunk_size,
    chunk_overlap,
    message: str,
) -> None:
    with pytest.raises(
        TypeError,
        match=message,
    ):
        TraceChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
