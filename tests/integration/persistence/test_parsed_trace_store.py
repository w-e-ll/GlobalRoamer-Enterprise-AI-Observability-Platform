from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from globalroamer_platform.bootstrap.parser_worker import (
    build_parser_worker,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_ARTIFACT_RECEIVED,
)
from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)
from globalroamer_platform.infrastructure.persistence.parsed_trace_store import (
    ParsedTraceStore,
)


SAMPLE_TRACE = Path("etc/sample_trace.csv")
TRACE_MAPPING = Path("etc/trace_mapping.yml")


@pytest.mark.asyncio
async def test_get_domain_reconstructs_persisted_parsed_trace() -> None:
    """
    ParsedTrace survives a persistence round trip.

    The parser worker creates and persists the aggregate. A new database
    session then reloads it through ParsedTraceStore.get_domain().
    """
    tenant_id = f"parsed-trace-store-{uuid4()}"
    trace_id = f"parsed-trace-{uuid4()}"
    testcase_id = "TC-ROUNDTRIP-001"

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
                "testcase_id": testcase_id,
            },
        )

        await worker.handle(incoming_event)
        await session.commit()

    async with async_session_factory() as session:
        store = ParsedTraceStore(session)

        loaded = await store.get_domain(
            tenant_id=tenant_id,
            trace_id=trace_id,
        )

    assert loaded is not None

    assert loaded.metadata["tenant_id"] == tenant_id
    assert loaded.metadata["trace_id"] == trace_id
    assert loaded.metadata["testcase_id"] == testcase_id

    assert loaded.source.tenant_id == tenant_id
    assert loaded.source.trace_id == trace_id
    assert loaded.source.testcase_id == testcase_id

    assert loaded.row_count == 3
    assert len(loaded.raw_trace.rows) == 3

    assert loaded.raw_trace.delimiter == ";"
    assert loaded.raw_trace.encoding

    assert loaded.extracted_value_count >= 0
    assert loaded.mapped_value_count >= 0
    assert loaded.evidence_count >= 0
    assert loaded.signal_count >= 0

    assert loaded.raw_trace.rows[0].line_number > 0
    assert loaded.raw_trace.rows[0].raw_fields
