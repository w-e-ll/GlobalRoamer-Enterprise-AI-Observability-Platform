from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from globalroamer_platform.bootstrap.chunk_worker import (
    build_chunk_worker,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_NORMALIZED,
)
from globalroamer_platform.domain.models.operational_event import (
    OperationalEvent,
    OperationalEventDirection,
    OperationalEventFamily,
    OperationalEventResult,
    OperationalEventSeverity,
)
from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)
from globalroamer_platform.infrastructure.models.outbox_message import (
    OutboxMessageModel,
)
from globalroamer_platform.infrastructure.database.models import (
    TraceChunkModel,
)
from globalroamer_platform.infrastructure.persistence.operational_event_store import (
    OperationalEventStore,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
)


TESTCASE_ID = "TC-CHUNK-INTEGRATION-001"


def build_operational_event(
    *,
    tenant_id: str,
    trace_id: str,
    sequence_number: int,
    source_line_number: int,
    event_name: str,
    normalized_message: str,
) -> OperationalEvent:
    """Create a complete OperationalEvent for the chunk worker test."""

    return OperationalEvent.create(
        tenant_id=tenant_id,
        trace_id=trace_id,
        testcase_id=TESTCASE_ID,
        sequence_number=sequence_number,
        event_name=event_name,
        event_family=OperationalEventFamily.AUTHENTICATION,
        severity=OperationalEventSeverity.MEDIUM,
        raw_message=(
            f"Raw trace event on source line "
            f"{source_line_number}"
        ),
        normalized_message=normalized_message,
        source_line_number=source_line_number,
        timestamp=datetime.now(timezone.utc),
        protocol_layer="NAS",
        direction=OperationalEventDirection.SEND,
        result=OperationalEventResult.OBSERVED,
        workflow_stage="authentication",
        network_domain="mobile_core",
        operator="Test Operator",
        country="Belgium",
        cause=None,
        retry_recommended=False,
        recommendation="Continue processing the trace",
        tags=(
            "authentication",
            "nas",
        ),
        evidence_lines=(
            f"line {source_line_number}: {normalized_message}",
        ),
        extracted_values={
            "imsi": "206010000000001",
            "protocol": "NAS",
        },
        metadata={
            "source": "pytest.integration.worker",
            "normalizer_version": "1.0",
        },
    )


def build_trace_normalized_event(
    *,
    tenant_id: str,
    trace_id: str,
) -> EventEnvelope:
    """Create the incoming TRACE_NORMALIZED event."""

    return EventEnvelope(
        event_id=uuid4(),
        event_type=TRACE_NORMALIZED,
        event_version=1,
        correlation_id=str(uuid4()),
        causation_id=None,
        tenant_id=tenant_id,
        occurred_at=datetime.now(timezone.utc),
        producer="pytest.integration.chunk-worker",
        payload={
            "trace_id": trace_id,
            "testcase_id": TESTCASE_ID,
            "operational_event_count": 3,
        },
    )


@pytest.mark.asyncio
async def test_chunk_worker_commits_trace_chunks_and_outbox_message() -> None:
    """TraceChunks and the outgoing outbox message are committed atomically."""

    tenant_id = f"chunk-worker-{uuid4()}"
    trace_id = f"chunk-trace-{uuid4()}"

    operational_events = (
        build_operational_event(
            tenant_id=tenant_id,
            trace_id=trace_id,
            sequence_number=1,
            source_line_number=10,
            event_name="authentication_request",
            normalized_message="Authentication request observed",
        ),
        build_operational_event(
            tenant_id=tenant_id,
            trace_id=trace_id,
            sequence_number=2,
            source_line_number=20,
            event_name="authentication_response",
            normalized_message="Authentication response observed",
        ),
        build_operational_event(
            tenant_id=tenant_id,
            trace_id=trace_id,
            sequence_number=3,
            source_line_number=30,
            event_name="authentication_complete",
            normalized_message="Authentication completed successfully",
        ),
    )

    async with async_session_factory() as session:
        operational_event_store = OperationalEventStore(
            session=session,
        )

        await operational_event_store.save_many(
            operational_events,
        )
        await session.commit()

    incoming_event = build_trace_normalized_event(
        tenant_id=tenant_id,
        trace_id=trace_id,
    )

    async with async_session_factory() as session:
        worker = build_chunk_worker(
            session=session,
        )

        outgoing_event = await worker.handle(
            incoming_event,
        )

        await session.commit()

    async with async_session_factory() as session:
        trace_chunks = tuple(
            (
                await session.scalars(
                    select(TraceChunkModel)
                    .where(
                        TraceChunkModel.tenant_id == tenant_id,
                        TraceChunkModel.trace_id == trace_id,
                    )
                    .order_by(
                        TraceChunkModel.chunk_index,
                    )
                )
            ).all()
        )

        outbox_message = await session.scalar(
            select(OutboxMessageModel).where(
                OutboxMessageModel.event_id
                == outgoing_event.event_id,
            )
        )

    assert trace_chunks

    assert all(
        chunk.tenant_id == tenant_id
        for chunk in trace_chunks
    )
    assert all(
        chunk.trace_id == trace_id
        for chunk in trace_chunks
    )
    assert all(
        chunk.testcase_id == TESTCASE_ID
        for chunk in trace_chunks
    )

    assert tuple(
        chunk.chunk_index
        for chunk in trace_chunks
    ) == tuple(
        range(len(trace_chunks))
    )

    assert outbox_message is not None
    assert outbox_message.event_type == "trace.chunked"
    assert outbox_message.tenant_id == tenant_id

    assert outgoing_event.event_type == "trace.chunked"
    assert outgoing_event.tenant_id == tenant_id
    assert outgoing_event.payload["trace_id"] == trace_id
    assert outgoing_event.payload["testcase_id"] == TESTCASE_ID


@pytest.mark.asyncio
async def test_chunk_worker_rolls_back_when_outbox_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure writing the outbox rolls back replacement TraceChunks."""

    tenant_id = f"chunk-rollback-{uuid4()}"
    trace_id = f"chunk-rollback-trace-{uuid4()}"

    operational_events = (
        build_operational_event(
            tenant_id=tenant_id,
            trace_id=trace_id,
            sequence_number=1,
            source_line_number=10,
            event_name="authentication_request",
            normalized_message="Authentication request observed",
        ),
        build_operational_event(
            tenant_id=tenant_id,
            trace_id=trace_id,
            sequence_number=2,
            source_line_number=20,
            event_name="authentication_response",
            normalized_message="Authentication response observed",
        ),
        build_operational_event(
            tenant_id=tenant_id,
            trace_id=trace_id,
            sequence_number=3,
            source_line_number=30,
            event_name="authentication_complete",
            normalized_message="Authentication completed successfully",
        ),
    )

    async with async_session_factory() as session:
        operational_event_store = OperationalEventStore(
            session=session,
        )

        await operational_event_store.save_many(
            operational_events,
        )
        await session.commit()

    incoming_event = build_trace_normalized_event(
        tenant_id=tenant_id,
        trace_id=trace_id,
    )

    async def failing_add(
        self,
        message,
    ) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        SQLAlchemyOutboxRepository,
        "add",
        failing_add,
    )

    async with async_session_factory() as session:
        worker = build_chunk_worker(
            session=session,
        )

        with pytest.raises(
            RuntimeError,
            match="boom",
        ):
            await worker.handle(
                incoming_event,
            )

        await session.rollback()

    async with async_session_factory() as session:
        trace_chunks = tuple(
            (
                await session.scalars(
                    select(TraceChunkModel).where(
                        TraceChunkModel.tenant_id == tenant_id,
                        TraceChunkModel.trace_id == trace_id,
                    )
                )
            ).all()
        )

        outbox_message = await session.scalar(
            select(OutboxMessageModel).where(
                OutboxMessageModel.tenant_id == tenant_id,
                OutboxMessageModel.event_type == "trace.chunked",
            )
        )

    assert trace_chunks == ()
    assert outbox_message is None
