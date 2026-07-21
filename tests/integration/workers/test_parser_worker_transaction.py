from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from globalroamer_platform.bootstrap.parser_worker import (
    build_parser_worker,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_ARTIFACT_RECEIVED,
)
from globalroamer_platform.infrastructure.models.outbox_message import (
    OutboxMessageModel,
)
from globalroamer_platform.infrastructure.models.parsed_trace import (
    ParsedTraceModel,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
)
from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)


SAMPLE_TRACE = Path("etc/sample_trace.csv")
TRACE_MAPPING = Path("etc/trace_mapping.yml")


@pytest.mark.asyncio
async def test_parser_worker_commits_parsed_trace_and_outbox_message() -> None:
    """ParsedTrace and OutboxMessage are committed atomically."""

    trace_id = f"parser-{uuid4()}"

    async with async_session_factory() as session:
        worker = build_parser_worker(
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

        incoming_event = EventEnvelope(
            event_id=uuid4(),
            event_type=TRACE_ARTIFACT_RECEIVED,
            event_version=1,
            correlation_id=str(uuid4()),
            causation_id=None,
            tenant_id="integration-test",
            occurred_at=datetime.now(timezone.utc),
            producer="pytest",
            payload={
                "source_path": SAMPLE_TRACE.name,
                "trace_id": trace_id,
                "testcase_id": "TC-001",
            },
        )

        outgoing_event = await worker.handle(
            incoming_event,
        )

        await session.commit()

    async with async_session_factory() as session:
        parsed_trace = await session.scalar(
            select(ParsedTraceModel).where(
                ParsedTraceModel.trace_id == trace_id,
            )
        )

        assert parsed_trace is not None
        assert parsed_trace.trace_id == trace_id
        assert parsed_trace.row_count == 3

        outbox = await session.scalar(
            select(OutboxMessageModel).where(
                OutboxMessageModel.event_id
                == outgoing_event.event_id,
            )
        )

        assert outbox is not None
        assert outbox.event_type == "trace.parsed"
        assert outbox.tenant_id == "integration-test"


@pytest.mark.asyncio
async def test_parser_worker_rolls_back_when_outbox_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure writing the outbox rolls back ParsedTrace."""

    trace_id = f"rollback-{uuid4()}"
    tenant_id = f"rollback-test-{uuid4()}"

    original_add = SQLAlchemyOutboxRepository.add

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
        worker = build_parser_worker(
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

        incoming_event = EventEnvelope(
            event_id=uuid4(),
            event_type=TRACE_ARTIFACT_RECEIVED,
            event_version=1,
            correlation_id=str(uuid4()),
            causation_id=None,
            tenant_id=tenant_id,
            occurred_at=datetime.now(timezone.utc),
            producer="pytest",
            payload={
                "source_path": SAMPLE_TRACE.name,
                "trace_id": trace_id,
                "testcase_id": "TC-001",
            },
        )

        with pytest.raises(RuntimeError):
            await worker.handle(
                incoming_event,
            )

        await session.rollback()

    monkeypatch.setattr(
        SQLAlchemyOutboxRepository,
        "add",
        original_add,
    )

    async with async_session_factory() as session:
        parsed_trace = await session.scalar(
            select(ParsedTraceModel).where(
                ParsedTraceModel.trace_id == trace_id,
            )
        )

        outbox = await session.scalar(
            select(OutboxMessageModel).where(
                OutboxMessageModel.tenant_id
                == tenant_id,
                OutboxMessageModel.event_type
                == "trace.parsed",
            )
        )

        assert parsed_trace is None
        assert outbox is None
