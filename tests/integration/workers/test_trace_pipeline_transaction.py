"""End-to-end integration test for the trace worker pipeline."""

from __future__ import annotations

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
from globalroamer_platform.domain.entities.source_artifact import (
    ArtifactStatus,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_CHUNKED,
    TRACE_NORMALIZED,
    TRACE_PARSED,
)
from globalroamer_platform.infrastructure.database.models import (
    TraceChunkModel,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_artifact_repository import (
    SQLAlchemyArtifactRepository,
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
from globalroamer_platform.infrastructure.persistence.operational_event_store import (
    OperationalEventStore,
)
from tests.integration.helpers.artifacts import (
    create_persisted_test_artifact,
)


SAMPLE_TRACE = Path("etc/sample_trace.csv")
TRACE_MAPPING = Path("etc/trace_mapping.yml")

TESTCASE_ID = "TC-PIPELINE-001"


@pytest.mark.asyncio
async def test_trace_pipeline_persists_every_stage_and_outbox_event(
    tmp_path: Path,
) -> None:
    """
    Execute the real parser, normalizer, and chunk workers in sequence.

    Every stage owns a separate database transaction:

        ObjectStorage
            -> SourceArtifact
            -> TRACE_ARTIFACT_RECEIVED

        TRACE_ARTIFACT_RECEIVED
            -> ParserWorker
            -> ParsedTrace
            -> TRACE_PARSED

        TRACE_PARSED
            -> NormalizerWorker
            -> OperationalEvent
            -> TRACE_NORMALIZED

        TRACE_NORMALIZED
            -> ChunkWorker
            -> TraceChunk
            -> TRACE_CHUNKED

    The test verifies persistence, event identity, causation, correlation,
    artifact propagation, and transactional outbox records across the complete
    pipeline.
    """

    tenant_id = f"pipeline-integration-{uuid4()}"
    trace_id = f"pipeline-trace-{uuid4()}"
    correlation_id = str(uuid4())
    storage_directory = tmp_path / "artifact-storage"

    # Stage 1:
    # Persist the source artifact, process it through ParserWorker, and commit:
    #
    # - SourceArtifact AVAILABLE -> PROCESSED;
    # - ParsedTrace;
    # - TRACE_PARSED outbox message.
    async with async_session_factory() as session:
        persisted_test_artifact = (
            await create_persisted_test_artifact(
                session=session,
                source_path=SAMPLE_TRACE,
                storage_directory=storage_directory,
                tenant_id=tenant_id,
                trace_id=trace_id,
                testcase_id=TESTCASE_ID,
                correlation_id=correlation_id,
                producer="pytest.integration.pipeline",
            )
        )

        artifact_id = (
            persisted_test_artifact.artifact.artifact_id
        )
        artifact_received_event = (
            persisted_test_artifact.event
        )

        parser_worker = build_parser_worker(
            session=session,
            trace_directory=storage_directory,
            artifact_storage_directory=storage_directory,
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

    # Stage 2:
    # Reload ParsedTrace, normalize it, persist OperationalEvents, and commit
    # TRACE_NORMALIZED to the transactional outbox.
    async with async_session_factory() as session:
        normalizer_worker = build_normalizer_worker(
            session=session,
        )

        normalized_event = (
            await normalizer_worker.handle(
                parsed_event,
            )
        )

        await session.commit()

    # Stage 3:
    # Reload OperationalEvents, create replacement chunks, and commit
    # TRACE_CHUNKED to the transactional outbox.
    async with async_session_factory() as session:
        chunk_worker = build_chunk_worker(
            session=session,
        )

        chunked_event = await chunk_worker.handle(
            normalized_event,
        )

        await session.commit()

    # Reload every persisted stage through a fresh database session.
    async with async_session_factory() as session:
        artifact_repository = (
            SQLAlchemyArtifactRepository(
                session=session,
            )
        )

        source_artifact = await artifact_repository.get(
            artifact_id,
        )

        parsed_trace = await session.scalar(
            select(ParsedTraceModel).where(
                ParsedTraceModel.tenant_id
                == tenant_id,
                ParsedTraceModel.trace_id
                == trace_id,
            )
        )

        operational_event_store = (
            OperationalEventStore(
                session=session,
            )
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
                        TraceChunkModel.tenant_id
                        == tenant_id,
                        TraceChunkModel.trace_id
                        == trace_id,
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
                    select(OutboxMessageModel)
                    .where(
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

    # Source artifact persistence and lifecycle.
    assert source_artifact.artifact_id == artifact_id
    assert source_artifact.tenant_id == tenant_id
    assert source_artifact.trace_id == trace_id
    assert source_artifact.testcase_id == TESTCASE_ID
    assert (
        source_artifact.status
        == ArtifactStatus.PROCESSED
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
        range(
            len(trace_chunks),
        )
    )

    # Event types.
    assert parsed_event.event_type == TRACE_PARSED
    assert (
        normalized_event.event_type
        == TRACE_NORMALIZED
    )
    assert chunked_event.event_type == TRACE_CHUNKED

    # Event versions.
    assert parsed_event.event_version == 1
    assert normalized_event.event_version == 1
    assert chunked_event.event_version == 1

    # Correlation ID remains stable through the complete pipeline.
    assert (
        artifact_received_event.correlation_id
        == correlation_id
    )
    assert parsed_event.correlation_id == correlation_id
    assert (
        normalized_event.correlation_id
        == correlation_id
    )
    assert chunked_event.correlation_id == correlation_id

    # Each outgoing event is caused by the event from the preceding stage.
    assert (
        parsed_event.causation_id
        == artifact_received_event.event_id
    )
    assert (
        normalized_event.causation_id
        == parsed_event.event_id
    )
    assert (
        chunked_event.causation_id
        == normalized_event.event_id
    )

    # Tenant identity remains stable through every stage.
    assert (
        artifact_received_event.tenant_id
        == tenant_id
    )
    assert parsed_event.tenant_id == tenant_id
    assert normalized_event.tenant_id == tenant_id
    assert chunked_event.tenant_id == tenant_id

    # Trace identity remains stable through every stage.
    assert (
        artifact_received_event.payload["trace_id"]
        == trace_id
    )
    assert parsed_event.payload["trace_id"] == trace_id
    assert (
        normalized_event.payload["trace_id"]
        == trace_id
    )
    assert chunked_event.payload["trace_id"] == trace_id

    # Test-case identity remains stable through every stage.
    assert (
        artifact_received_event.payload["testcase_id"]
        == TESTCASE_ID
    )
    assert (
        parsed_event.payload["testcase_id"]
        == TESTCASE_ID
    )
    assert (
        normalized_event.payload["testcase_id"]
        == TESTCASE_ID
    )
    assert (
        chunked_event.payload["testcase_id"]
        == TESTCASE_ID
    )

    # Artifact identity enters through TRACE_ARTIFACT_RECEIVED and is
    # propagated by the parser stage.
    assert (
        artifact_received_event.payload["artifact_id"]
        == str(artifact_id)
    )
    assert (
        parsed_event.payload["artifact_id"]
        == str(artifact_id)
    )

    # Parsed-trace identity is propagated into normalization.
    assert (
        normalized_event.payload["parsed_trace_id"]
        == parsed_event.payload["parsed_trace_id"]
    )

    # Summary data agrees with persisted state.
    assert (
        normalized_event.payload[
            "operational_event_count"
        ]
        == len(operational_events)
    )

    assert (
        chunked_event.payload["chunk_count"]
        == len(trace_chunks)
    )

    # Every worker created exactly one transactional outbox message.
    assert len(outbox_messages) == 3

    outbox_by_event_id = {
        message.event_id: message
        for message in outbox_messages
    }

    assert set(outbox_by_event_id) == {
        parsed_event.event_id,
        normalized_event.event_id,
        chunked_event.event_id,
    }

    parsed_outbox = outbox_by_event_id[
        parsed_event.event_id
    ]
    normalized_outbox = outbox_by_event_id[
        normalized_event.event_id
    ]
    chunked_outbox = outbox_by_event_id[
        chunked_event.event_id
    ]

    assert parsed_outbox.event_type == TRACE_PARSED
    assert (
        normalized_outbox.event_type
        == TRACE_NORMALIZED
    )
    assert chunked_outbox.event_type == TRACE_CHUNKED

    assert all(
        message.tenant_id == tenant_id
        for message in outbox_messages
    )

    assert all(
        message.correlation_id == correlation_id
        for message in outbox_messages
    )

    # Persisted outbox payloads preserve stage identity.
    assert (
        parsed_outbox.payload["artifact_id"]
        == str(artifact_id)
    )
    assert (
        parsed_outbox.payload["trace_id"]
        == trace_id
    )
    assert (
        parsed_outbox.payload["testcase_id"]
        == TESTCASE_ID
    )

    assert (
        normalized_outbox.payload["trace_id"]
        == trace_id
    )
    assert (
        normalized_outbox.payload["testcase_id"]
        == TESTCASE_ID
    )
    assert (
        normalized_outbox.payload[
            "parsed_trace_id"
        ]
        == parsed_event.payload["parsed_trace_id"]
    )

    assert (
        chunked_outbox.payload["trace_id"]
        == trace_id
    )
    assert (
        chunked_outbox.payload["testcase_id"]
        == TESTCASE_ID
    )
    assert (
        chunked_outbox.payload["chunk_count"]
        == len(trace_chunks)
    )

    # Persisted outbox causation mirrors the in-memory event chain.
    assert (
        parsed_outbox.causation_id
        == artifact_received_event.event_id
    )
    assert (
        normalized_outbox.causation_id
        == parsed_event.event_id
    )
    assert (
        chunked_outbox.causation_id
        == normalized_event.event_id
    )
