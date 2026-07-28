"""Integration tests for the normalizer worker transaction boundary."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from globalroamer_platform.bootstrap.normalizer_worker import (
    build_normalizer_worker,
)
from globalroamer_platform.bootstrap.parser_worker import (
    build_parser_worker,
)
from globalroamer_platform.domain.entities.source_artifact import (
    ArtifactStatus,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_NORMALIZED,
    TRACE_PARSED,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_artifact_repository import (
    SQLAlchemyArtifactRepository,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
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

TESTCASE_ID = "TC-001"


async def create_persisted_parsed_trace(
    *,
    tenant_id: str,
    trace_id: str,
    storage_directory: Path,
    correlation_id: str | None = None,
) -> tuple[EventEnvelope, object]:
    """
    Persist a real source artifact and process it through ParserWorker.

    The setup mirrors the production flow:

        ObjectStorage
            -> SourceArtifact
            -> TRACE_ARTIFACT_RECEIVED
            -> ParserWorker
            -> ParsedTrace
            -> TRACE_PARSED

    The parser transaction is committed before the normalizer transaction
    begins.

    Returns:
        A tuple containing the committed TRACE_PARSED event and artifact ID.
    """

    normalized_correlation_id = (
        correlation_id
        if correlation_id is not None
        else str(uuid4())
    )

    async with async_session_factory() as session:
        persisted_artifact = (
            await create_persisted_test_artifact(
                session=session,
                source_path=SAMPLE_TRACE,
                storage_directory=storage_directory,
                tenant_id=tenant_id,
                trace_id=trace_id,
                testcase_id=TESTCASE_ID,
                correlation_id=normalized_correlation_id,
                producer="pytest.normalizer-setup",
            )
        )

        artifact_id = (
            persisted_artifact.artifact.artifact_id
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
            persisted_artifact.event,
        )

        await session.commit()

    assert parsed_event.event_type == TRACE_PARSED
    assert (
        parsed_event.payload["artifact_id"]
        == str(artifact_id)
    )
    assert parsed_event.payload["trace_id"] == trace_id
    assert (
        parsed_event.payload["testcase_id"]
        == TESTCASE_ID
    )

    return parsed_event, artifact_id


@pytest.mark.asyncio
async def test_normalizer_worker_commits_operational_events_and_outbox(
    tmp_path: Path,
) -> None:
    """
    A persisted ParsedTrace is normalized and committed atomically.

    The parser setup transaction commits:

    - the SourceArtifact in PROCESSED state;
    - the ParsedTrace snapshot;
    - one TRACE_PARSED outbox message.

    The normalizer transaction then commits:

    - normalized OperationalEvent rows;
    - one TRACE_NORMALIZED transactional outbox message.
    """

    tenant_id = f"normalizer-test-{uuid4()}"
    trace_id = f"normalizer-{uuid4()}"
    correlation_id = str(uuid4())
    storage_directory = tmp_path / "artifact-storage"

    parsed_event, artifact_id = (
        await create_persisted_parsed_trace(
            tenant_id=tenant_id,
            trace_id=trace_id,
            storage_directory=storage_directory,
            correlation_id=correlation_id,
        )
    )

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

    assert normalized_event.event_type == TRACE_NORMALIZED
    assert normalized_event.event_version == 1
    assert normalized_event.tenant_id == tenant_id
    assert (
        normalized_event.correlation_id
        == correlation_id
    )
    assert (
        normalized_event.causation_id
        == parsed_event.event_id
    )

    assert (
        normalized_event.payload["trace_id"]
        == trace_id
    )
    assert (
        normalized_event.payload["parsed_trace_id"]
        == parsed_event.payload["parsed_trace_id"]
    )
    assert (
        normalized_event.payload["testcase_id"]
        == TESTCASE_ID
    )

    assert (
        normalized_event.payload[
            "source_evidence_count"
        ]
        == parsed_event.payload["evidence_count"]
    )

    assert (
        normalized_event.payload[
            "operational_event_count"
        ]
        >= 0
    )
    assert (
        normalized_event.payload[
            "failure_event_count"
        ]
        >= 0
    )
    assert (
        normalized_event.payload[
            "high_severity_event_count"
        ]
        >= 0
    )
    assert (
        normalized_event.payload[
            "retry_recommended_count"
        ]
        >= 0
    )

    async with async_session_factory() as session:
        artifact_repository = (
            SQLAlchemyArtifactRepository(
                session=session,
            )
        )

        persisted_artifact = (
            await artifact_repository.get(
                artifact_id,
            )
        )

        persisted_trace = await session.scalar(
            select(ParsedTraceModel).where(
                ParsedTraceModel.tenant_id
                == tenant_id,
                ParsedTraceModel.trace_id
                == trace_id,
            )
        )

        parsed_outbox = await session.scalar(
            select(OutboxMessageModel).where(
                OutboxMessageModel.event_id
                == parsed_event.event_id,
            )
        )

        normalized_outbox = await session.scalar(
            select(OutboxMessageModel).where(
                OutboxMessageModel.event_id
                == normalized_event.event_id,
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

    assert (
        persisted_artifact.status
        == ArtifactStatus.PROCESSED
    )
    assert persisted_artifact.tenant_id == tenant_id
    assert persisted_artifact.trace_id == trace_id
    assert (
        persisted_artifact.testcase_id
        == TESTCASE_ID
    )

    assert persisted_trace is not None
    assert persisted_trace.trace_id == trace_id
    assert persisted_trace.tenant_id == tenant_id
    assert persisted_trace.testcase_id == TESTCASE_ID

    assert parsed_outbox is not None
    assert parsed_outbox.event_type == TRACE_PARSED
    assert parsed_outbox.tenant_id == tenant_id
    assert (
        parsed_outbox.correlation_id
        == correlation_id
    )
    assert (
        parsed_outbox.payload["artifact_id"]
        == str(artifact_id)
    )

    assert normalized_outbox is not None
    assert (
        normalized_outbox.event_type
        == TRACE_NORMALIZED
    )
    assert normalized_outbox.tenant_id == tenant_id
    assert (
        normalized_outbox.correlation_id
        == correlation_id
    )
    assert (
        normalized_outbox.causation_id
        == parsed_event.event_id
    )
    assert (
        normalized_outbox.payload["trace_id"]
        == trace_id
    )
    assert (
        normalized_outbox.payload[
            "parsed_trace_id"
        ]
        == parsed_event.payload[
            "parsed_trace_id"
        ]
    )
    assert (
        normalized_outbox.payload["testcase_id"]
        == TESTCASE_ID
    )

    assert len(operational_events) == (
        normalized_event.payload[
            "operational_event_count"
        ]
    )

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


@pytest.mark.asyncio
async def test_normalizer_worker_rolls_back_operational_events_when_outbox_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    Failure writing TRACE_NORMALIZED rolls back the normalizer transaction.

    The parser transaction was committed earlier, so these remain available:

    - the PROCESSED SourceArtifact;
    - the ParsedTrace snapshot;
    - the TRACE_PARSED outbox message.

    The failed normalizer transaction commits neither:

    - OperationalEvent rows;
    - a TRACE_NORMALIZED outbox message.
    """

    tenant_id = f"normalizer-rollback-{uuid4()}"
    trace_id = f"normalizer-rollback-{uuid4()}"
    correlation_id = str(uuid4())
    storage_directory = tmp_path / "artifact-storage"

    parsed_event, artifact_id = (
        await create_persisted_parsed_trace(
            tenant_id=tenant_id,
            trace_id=trace_id,
            storage_directory=storage_directory,
            correlation_id=correlation_id,
        )
    )

    async def failing_add(
        self: SQLAlchemyOutboxRepository,
        message: object,
    ) -> None:
        del self
        del message

        raise RuntimeError(
            "simulated normalized outbox failure"
        )

    monkeypatch.setattr(
        SQLAlchemyOutboxRepository,
        "add",
        failing_add,
    )

    async with async_session_factory() as session:
        normalizer_worker = build_normalizer_worker(
            session=session,
        )

        with pytest.raises(
            RuntimeError,
            match="simulated normalized outbox failure",
        ):
            await normalizer_worker.handle(
                parsed_event,
            )

        await session.rollback()

    async with async_session_factory() as session:
        artifact_repository = (
            SQLAlchemyArtifactRepository(
                session=session,
            )
        )

        persisted_artifact = (
            await artifact_repository.get(
                artifact_id,
            )
        )

        persisted_trace = await session.scalar(
            select(ParsedTraceModel).where(
                ParsedTraceModel.tenant_id
                == tenant_id,
                ParsedTraceModel.trace_id
                == trace_id,
            )
        )

        normalized_outbox = await session.scalar(
            select(OutboxMessageModel).where(
                OutboxMessageModel.tenant_id
                == tenant_id,
                OutboxMessageModel.event_type
                == TRACE_NORMALIZED,
            )
        )

        parsed_outbox = await session.scalar(
            select(OutboxMessageModel).where(
                OutboxMessageModel.event_id
                == parsed_event.event_id,
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

    # The parser transaction was committed before normalizer processing.
    assert (
        persisted_artifact.status
        == ArtifactStatus.PROCESSED
    )
    assert persisted_artifact.tenant_id == tenant_id
    assert persisted_artifact.trace_id == trace_id
    assert (
        persisted_artifact.testcase_id
        == TESTCASE_ID
    )

    assert persisted_trace is not None
    assert persisted_trace.tenant_id == tenant_id
    assert persisted_trace.trace_id == trace_id
    assert persisted_trace.testcase_id == TESTCASE_ID

    assert parsed_outbox is not None
    assert parsed_outbox.event_type == TRACE_PARSED
    assert parsed_outbox.tenant_id == tenant_id
    assert (
        parsed_outbox.correlation_id
        == correlation_id
    )
    assert (
        parsed_outbox.payload["artifact_id"]
        == str(artifact_id)
    )

    # The failed normalizer transaction committed nothing.
    assert normalized_outbox is None
    assert operational_events == ()
