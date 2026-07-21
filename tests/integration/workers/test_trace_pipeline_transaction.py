from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from globalroamer_platform.bootstrap.chunk_worker import (
    build_chunk_worker,
)
from globalroamer_platform.bootstrap.normalizer_worker import (
    build_normalizer_worker,
)
from globalroamer_platform.bootstrap.parser_worker import (
    build_parser_worker,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_ARTIFACT_RECEIVED,
    TRACE_CHUNKED,
    TRACE_NORMALIZED,
    TRACE_PARSED,
)
from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)
from globalroamer_platform.infrastructure.models.outbox_message import (
    OutboxMessageModel,
)
from globalroamer_platform.infrastructure.models.parsed_trace import (
    ParsedTraceModel,
)
from globalroamer_platform.infrastructure.database.models import (
    TraceChunkModel,
)
from globalroamer_platform.infrastructure.persistence.operational_event_store import (
    OperationalEventStore,
)


SAMPLE_TRACE = Path("etc/sample_trace.csv")
TRACE_MAPPING = Path("etc/trace_mapping.yml")

TESTCASE_ID = "TC-PIPELINE-001"


@pytest.mark.asyncio
async def test_trace_pipeline_persists_every_stage_and_outbox_event() -> None:
    """
    The real parser, normalizer, and chunk workers execute in sequence.

    Every stage owns a separate database transaction:

    TRACE_ARTIFACT_RECEIVED
        -> ParserWorker
        -> TRACE_PARSED

    TRACE_PARSED
        -> NormalizerWorker
        -> TRACE_NORMALIZED

    TRACE_NORMALIZED
        -> ChunkWorker
        -> TRACE_CHUNKED
    """

    tenant_id = f"pipeline-integration-{uuid4()}"
    trace_id = f"pipeline-trace-{uuid4()}"
    correlation_id = str(uuid4())

    artifact_received_event = EventEnvelope(
        event_id=uuid4(),
        event_type=TRACE_ARTIFACT_RECEIVED,
        event_version=1,
        correlation_id=correlation_id,
        causation_id=None,
        tenant_id=tenant_id,
        occurred_at=datetime.now(timezone.utc),
        producer="pytest.integration.pipeline",
        payload={
            "source_path": SAMPLE_TRACE.name,
            "trace_id": trace_id,
            "testcase_id": TESTCASE_ID,
        },
    )

    # Stage 1: parse the source artifact and commit ParsedTrace +
    # TRACE_PARSED outbox message.
    async with async_session_factory() as session:
        parser_worker = build_parser_worker(
            session=session,
            trace_directory=SAMPLE_TRACE.parent,
            mapping_configuration_path=TRACE_MAPPING,
            source_timezone="UTC",
            target_timezone="UTC",
            supported_extensions=[
                SAMPLE_TRACE.suffix,
            ],
            max_file_size_mb=100,
        )

        parsed_event = await parser_worker.handle(
            artifact_received_event,
        )

        await session.commit()

    # Stage 2: reload the ParsedTrace, normalize it, persist
    # OperationalEvents, and commit TRACE_NORMALIZED to the outbox.
    async with async_session_factory() as session:
        normalizer_worker = build_normalizer_worker(
            session=session,
        )

        normalized_event = await normalizer_worker.handle(
            parsed_event,
        )

        await session.commit()

    # Stage 3: reload OperationalEvents, build replacement chunks,
    # and commit TRACE_CHUNKED to the outbox.
    async with async_session_factory() as session:
        chunk_worker = build_chunk_worker(
            session=session,
        )

        chunked_event = await chunk_worker.handle(
            normalized_event,
        )

        await session.commit()

    # Reload all persisted state through a fresh session.
    async with async_session_factory() as session:
        parsed_trace = await session.scalar(
            select(ParsedTraceModel).where(
                ParsedTraceModel.tenant_id == tenant_id,
                ParsedTraceModel.trace_id == trace_id,
            )
        )

        operational_event_store = OperationalEventStore(
            session=session,
        )

        operational_events = (
            await operational_event_store.list_by_trace(
                tenant_id=tenant_id,
                trace_id=trace_id,
            )
        )

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

        outbox_messages = tuple(
            (
                await session.scalars(
                    select(OutboxMessageModel).where(
                        OutboxMessageModel.event_id.in_(
                            (
                                parsed_event.event_id,
                                normalized_event.event_id,
                                chunked_event.event_id,
                            )
                        )
                    )
                )
            ).all()
        )

    # Parser persistence.
    assert parsed_trace is not None
    assert parsed_trace.tenant_id == tenant_id
    assert parsed_trace.trace_id == trace_id
    assert parsed_trace.testcase_id == TESTCASE_ID
    assert parsed_trace.row_count == 3

    # Normalizer persistence.
    assert operational_events
    assert all(
        event.tenant_id == tenant_id
        for event in operational_events
    )
    assert all(
        event.trace_id == trace_id
        for event in operational_events
    )
    assert all(
        event.testcase_id == TESTCASE_ID
        for event in operational_events
    )

    assert tuple(
        event.sequence_number
        for event in operational_events
    ) == tuple(
        sorted(
            event.sequence_number
            for event in operational_events
        )
    )

    # Chunk persistence.
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

    # Event types.
    assert parsed_event.event_type == TRACE_PARSED
    assert normalized_event.event_type == TRACE_NORMALIZED
    assert chunked_event.event_type == TRACE_CHUNKED

    # Correlation ID remains stable through the complete pipeline.
    assert parsed_event.correlation_id == correlation_id
    assert normalized_event.correlation_id == correlation_id
    assert chunked_event.correlation_id == correlation_id

    # Each outgoing event is caused by the preceding event.
    assert parsed_event.causation_id == (
        artifact_received_event.event_id
    )
    assert normalized_event.causation_id == (
        parsed_event.event_id
    )
    assert chunked_event.causation_id == (
        normalized_event.event_id
    )

    # Identity remains stable through every stage.
    assert parsed_event.tenant_id == tenant_id
    assert normalized_event.tenant_id == tenant_id
    assert chunked_event.tenant_id == tenant_id

    assert parsed_event.payload["trace_id"] == trace_id
    assert normalized_event.payload["trace_id"] == trace_id
    assert chunked_event.payload["trace_id"] == trace_id

    assert parsed_event.payload["testcase_id"] == TESTCASE_ID
    assert (
        normalized_event.payload["testcase_id"]
        == TESTCASE_ID
    )
    assert chunked_event.payload["testcase_id"] == TESTCASE_ID

    # Summary data agrees with persisted state.
    assert (
        normalized_event.payload["operational_event_count"]
        == len(operational_events)
    )
    assert (
        chunked_event.payload["chunk_count"]
        == len(trace_chunks)
    )

    # Every worker created one transactional outbox message.
    assert len(outbox_messages) == 3

    outbox_by_event_id = {
        message.event_id: message
        for message in outbox_messages
    }

    assert (
        outbox_by_event_id[
            parsed_event.event_id
        ].event_type
        == TRACE_PARSED
    )
    assert (
        outbox_by_event_id[
            normalized_event.event_id
        ].event_type
        == TRACE_NORMALIZED
    )
    assert (
        outbox_by_event_id[
            chunked_event.event_id
        ].event_type
        == TRACE_CHUNKED
    )

    assert all(
        message.tenant_id == tenant_id
        for message in outbox_messages
    )
    assert all(
        message.correlation_id == correlation_id
        for message in outbox_messages
    )
