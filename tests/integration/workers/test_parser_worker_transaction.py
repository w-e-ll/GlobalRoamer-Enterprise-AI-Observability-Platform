"""Integration tests for the parser worker transaction boundary."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from globalroamer_platform.bootstrap.parser_worker import (
    build_parser_worker,
)
from globalroamer_platform.domain.entities.source_artifact import (
    ArtifactStatus,
)
from globalroamer_platform.domain.events.event_types import (
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
from tests.integration.helpers.artifacts import (
    create_persisted_test_artifact,
)


SAMPLE_TRACE = Path("etc/sample_trace.csv")
TRACE_MAPPING = Path("etc/trace_mapping.yml")

TESTCASE_ID = "TC-001"


@pytest.mark.asyncio
async def test_parser_worker_commits_parsed_trace_and_outbox_message(
    tmp_path: Path,
) -> None:
    """
    Parser processing commits all database changes atomically.

    The transaction persists:

    - the ParsedTrace snapshot;
    - the TRACE_PARSED outbox message;
    - the SourceArtifact transition from AVAILABLE to PROCESSED.
    """

    tenant_id = f"parser-integration-{uuid4()}"
    trace_id = f"parser-{uuid4()}"
    correlation_id = str(uuid4())
    storage_directory = tmp_path / "artifact-storage"

    async with async_session_factory() as session:
        persisted_artifact = (
            await create_persisted_test_artifact(
                session=session,
                source_path=SAMPLE_TRACE,
                storage_directory=storage_directory,
                tenant_id=tenant_id,
                trace_id=trace_id,
                testcase_id=TESTCASE_ID,
                correlation_id=correlation_id,
                producer="pytest.parser-worker",
            )
        )

        artifact_id = (
            persisted_artifact.artifact.artifact_id
        )
        incoming_event = persisted_artifact.event

        worker = build_parser_worker(
            session=session,
            trace_directory=storage_directory,
            artifact_storage_directory=(
                storage_directory
            ),
            mapping_configuration_path=TRACE_MAPPING,
            source_timezone="UTC",
            target_timezone="UTC",
            supported_extensions=[
                SAMPLE_TRACE.suffix,
            ],
            max_file_size_mb=100,
        )

        outgoing_event = await worker.handle(
            incoming_event,
        )

        await session.commit()

    assert outgoing_event.event_type == TRACE_PARSED
    assert outgoing_event.event_version == 1
    assert outgoing_event.tenant_id == tenant_id
    assert (
        outgoing_event.correlation_id
        == correlation_id
    )
    assert (
        outgoing_event.causation_id
        == incoming_event.event_id
    )

    assert (
        outgoing_event.payload["artifact_id"]
        == str(artifact_id)
    )
    assert (
        outgoing_event.payload["trace_id"]
        == trace_id
    )
    assert (
        outgoing_event.payload["testcase_id"]
        == TESTCASE_ID
    )
    assert outgoing_event.payload["row_count"] == 3

    async with async_session_factory() as session:
        artifact_repository = (
            SQLAlchemyArtifactRepository(
                session=session,
            )
        )

        persisted_source_artifact = (
            await artifact_repository.get(
                artifact_id,
            )
        )

        parsed_trace = await session.scalar(
            select(ParsedTraceModel).where(
                ParsedTraceModel.tenant_id
                == tenant_id,
                ParsedTraceModel.trace_id
                == trace_id,
            )
        )

        outbox = await session.scalar(
            select(OutboxMessageModel).where(
                OutboxMessageModel.event_id
                == outgoing_event.event_id,
            )
        )

    assert (
        persisted_source_artifact.artifact_id
        == artifact_id
    )
    assert (
        persisted_source_artifact.status
        == ArtifactStatus.PROCESSED
    )
    assert (
        persisted_source_artifact.tenant_id
        == tenant_id
    )
    assert (
        persisted_source_artifact.trace_id
        == trace_id
    )
    assert (
        persisted_source_artifact.testcase_id
        == TESTCASE_ID
    )

    assert parsed_trace is not None
    assert parsed_trace.tenant_id == tenant_id
    assert parsed_trace.trace_id == trace_id
    assert parsed_trace.testcase_id == TESTCASE_ID
    assert parsed_trace.row_count == 3

    assert outbox is not None
    assert outbox.event_type == TRACE_PARSED
    assert outbox.tenant_id == tenant_id
    assert outbox.correlation_id == correlation_id
    assert outbox.payload["artifact_id"] == str(
        artifact_id,
    )
    assert outbox.payload["trace_id"] == trace_id
    assert (
        outbox.payload["testcase_id"]
        == TESTCASE_ID
    )


@pytest.mark.asyncio
async def test_parser_worker_rolls_back_when_outbox_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    Failure writing TRACE_PARSED rolls back parser processing.

    The artifact setup is committed in an earlier transaction. The parser
    transaction then attempts to persist:

    - the AVAILABLE-to-PROCESSING artifact transition;
    - the ParsedTrace snapshot;
    - the PROCESSING-to-PROCESSED artifact transition;
    - the TRACE_PARSED outbox message.

    When outbox persistence fails, all changes from the parser transaction
    are rolled back and the previously committed artifact remains AVAILABLE.
    """

    tenant_id = f"parser-rollback-{uuid4()}"
    trace_id = f"rollback-{uuid4()}"
    correlation_id = str(uuid4())
    storage_directory = tmp_path / "artifact-storage"

    # Persist and commit the source artifact independently. This represents
    # the completed submission transaction that occurred before the parser
    # worker consumed its event.
    async with async_session_factory() as session:
        persisted_artifact = (
            await create_persisted_test_artifact(
                session=session,
                source_path=SAMPLE_TRACE,
                storage_directory=storage_directory,
                tenant_id=tenant_id,
                trace_id=trace_id,
                testcase_id=TESTCASE_ID,
                correlation_id=correlation_id,
                producer="pytest.parser-worker",
            )
        )

        artifact_id = (
            persisted_artifact.artifact.artifact_id
        )
        incoming_event = persisted_artifact.event

        await session.commit()

    async def failing_add(
        self: SQLAlchemyOutboxRepository,
        message: object,
    ) -> None:
        del self
        del message

        raise RuntimeError(
            "simulated parsed outbox failure"
        )

    monkeypatch.setattr(
        SQLAlchemyOutboxRepository,
        "add",
        failing_add,
    )

    # Execute parser processing in a new transaction. The artificial outbox
    # failure must roll back the parsed trace and both artifact transitions.
    async with async_session_factory() as session:
        worker = build_parser_worker(
            session=session,
            trace_directory=storage_directory,
            artifact_storage_directory=(
                storage_directory
            ),
            mapping_configuration_path=TRACE_MAPPING,
            source_timezone="UTC",
            target_timezone="UTC",
            supported_extensions=[
                SAMPLE_TRACE.suffix,
            ],
            max_file_size_mb=100,
        )

        with pytest.raises(
            RuntimeError,
            match="simulated parsed outbox failure",
        ):
            await worker.handle(
                incoming_event,
            )

        await session.rollback()

    async with async_session_factory() as session:
        artifact_repository = (
            SQLAlchemyArtifactRepository(
                session=session,
            )
        )

        persisted_source_artifact = (
            await artifact_repository.get(
                artifact_id,
            )
        )

        parsed_trace = await session.scalar(
            select(ParsedTraceModel).where(
                ParsedTraceModel.tenant_id
                == tenant_id,
                ParsedTraceModel.trace_id
                == trace_id,
            )
        )

        parsed_outbox = await session.scalar(
            select(OutboxMessageModel).where(
                OutboxMessageModel.tenant_id
                == tenant_id,
                OutboxMessageModel.event_type
                == TRACE_PARSED,
            )
        )

    # The source artifact was committed by the earlier submission-style
    # transaction and therefore remains present.
    assert (
        persisted_source_artifact.artifact_id
        == artifact_id
    )
    assert (
        persisted_source_artifact.status
        == ArtifactStatus.AVAILABLE
    )
    assert (
        persisted_source_artifact.tenant_id
        == tenant_id
    )
    assert (
        persisted_source_artifact.trace_id
        == trace_id
    )

    # The failed parser transaction committed nothing.
    assert parsed_trace is None
    assert parsed_outbox is None
