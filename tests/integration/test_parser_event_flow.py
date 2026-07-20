from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from globalroamer_platform.application.traces.process_trace import (
    ProcessTraceResult,
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


def make_event() -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_type=TRACE_ARTIFACT_RECEIVED,
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
        row_count=100,
        evidence_count=12,
        signal_count=5,
        warning_count=1,
        error_count=0,
        is_valid=True,
        is_complete=True,
    )


@pytest.mark.anyio
async def test_parser_event_flow() -> None:
    process_trace = AsyncMock()
    process_trace.execute.return_value = make_result()

    parser_worker = ParserWorker(
        process_trace=process_trace,
    )

    publisher_adapter = InMemoryEventPublisher()

    outbox = OutboxPublisher(
        event_publisher=publisher_adapter,
    )

    incoming = make_event()

    parsed_event = await parser_worker.handle(incoming)

    await outbox.publish(parsed_event)

    assert publisher_adapter.event_count == 1

    published = publisher_adapter.last_event()

    assert published is not None

    assert published.event_type == TRACE_PARSED
    assert published.correlation_id == incoming.correlation_id
    assert published.causation_id == incoming.event_id
    assert published.tenant_id == incoming.tenant_id

    assert published.payload["trace_id"] == "trace-001"
    assert published.payload["testcase_id"] == "TC-001"
    assert published.payload["row_count"] == 100
    assert published.payload["evidence_count"] == 12
    assert published.payload["signal_count"] == 5
    assert published.payload["warning_count"] == 1
    assert published.payload["error_count"] == 0
    assert published.payload["is_valid"] is True
    assert published.payload["is_complete"] is True

    process_trace.execute.assert_awaited_once()
