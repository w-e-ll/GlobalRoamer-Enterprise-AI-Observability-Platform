from __future__ import annotations

from datetime import datetime, timezone
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
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_ARTIFACT_RECEIVED,
    TRACE_NORMALIZED,
    TRACE_PARSED,
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


SAMPLE_TRACE = Path("etc/sample_trace.csv")
TRACE_MAPPING = Path("etc/trace_mapping.yml")


async def create_persisted_parsed_trace(
    *,
    tenant_id: str,
    trace_id: str,
) -> EventEnvelope:
    """
    Run the real parser worker and commit a ParsedTrace snapshot.

    Returns the TRACE_PARSED event that should be consumed by the
    normalizer worker.
    """
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

        parsed_event = await parser_worker.handle(
            incoming_event,
        )

        await session.commit()

    assert parsed_event.event_type == TRACE_PARSED

    return parsed_event


@pytest.mark.asyncio
async def test_normalizer_worker_commits_operational_events_and_outbox() -> None:
    """
    A persisted ParsedTrace is normalized and committed atomically.

    The transaction persists:

    - normalized OperationalEvent rows;
    - one TRACE_NORMALIZED transactional outbox message.

    Both are visible from a new database session after commit.
    """
    tenant_id = f"normalizer-test-{uuid4()}"
    trace_id = f"normalizer-{uuid4()}"

    parsed_event = await create_persisted_parsed_trace(
        tenant_id=tenant_id,
        trace_id=trace_id,
    )

    async with async_session_factory() as session:
        normalizer_worker = build_normalizer_worker(
            session=session,
        )

        normalized_event = await normalizer_worker.handle(
            parsed_event,
        )

        await session.commit()

    assert normalized_event.event_type == TRACE_NORMALIZED
    assert normalized_event.event_version == 1
    assert normalized_event.tenant_id == tenant_id
    assert normalized_event.correlation_id == (
        parsed_event.correlation_id
    )
    assert normalized_event.causation_id == (
        parsed_event.event_id
    )

    assert normalized_event.payload["trace_id"] == trace_id
    assert (
        normalized_event.payload["parsed_trace_id"]
        == parsed_event.payload["parsed_trace_id"]
    )
    assert (
        normalized_event.payload["testcase_id"]
        == "TC-001"
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
                OutboxMessageModel.event_id
                == normalized_event.event_id,
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

        assert persisted_trace is not None
        assert persisted_trace.trace_id == trace_id
        assert persisted_trace.tenant_id == tenant_id

        assert normalized_outbox is not None
        assert (
            normalized_outbox.event_type
            == TRACE_NORMALIZED
        )
        assert normalized_outbox.tenant_id == tenant_id
        assert (
            normalized_outbox.correlation_id
            == parsed_event.correlation_id
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
) -> None:
    """
    A failure writing TRACE_NORMALIZED rolls back the complete transaction.

    The ParsedTrace and TRACE_PARSED outbox message were committed in the
    earlier parser transaction, so they remain available.

    The normalizer transaction commits neither:

    - OperationalEvent rows;
    - TRACE_NORMALIZED outbox message.
    """
    tenant_id = f"normalizer-rollback-{uuid4()}"
    trace_id = f"normalizer-rollback-{uuid4()}"

    parsed_event = await create_persisted_parsed_trace(
        tenant_id=tenant_id,
        trace_id=trace_id,
    )

    async def failing_add(
        self: SQLAlchemyOutboxRepository,
        message,
    ) -> None:
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

        operational_event_store = OperationalEventStore(
            session=session,
        )

        operational_events = (
            await operational_event_store.list_by_trace(
                tenant_id=tenant_id,
                trace_id=trace_id,
            )
        )

        # The parser transaction was committed earlier.
        assert persisted_trace is not None
        assert parsed_outbox is not None
        assert parsed_outbox.event_type == TRACE_PARSED

        # The failed normalizer transaction committed nothing.
        assert normalized_outbox is None
        assert operational_events == ()
