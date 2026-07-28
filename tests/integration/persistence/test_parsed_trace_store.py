from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from globalroamer_platform.bootstrap.parser_worker import (
    build_parser_worker,
)
from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)
from globalroamer_platform.infrastructure.persistence.parsed_trace_store import (
    ParsedTraceStore,
)
from tests.integration.helpers.artifacts import (
    create_persisted_test_artifact,
)


SAMPLE_TRACE = Path("etc/sample_trace.csv")
TRACE_MAPPING = Path("etc/trace_mapping.yml")


@pytest.mark.asyncio
async def test_get_domain_reconstructs_persisted_parsed_trace(
    tmp_path: Path,
) -> None:
    """
    ParsedTrace survives a persistence round trip.

    The test persists a source artifact through the same storage and
    repository contract used by production. The parser worker processes the
    resulting TRACE_ARTIFACT_RECEIVED event and persists the ParsedTrace
    aggregate. A new database session then reloads the aggregate through
    ParsedTraceStore.get_domain().
    """

    tenant_id = f"parsed-trace-store-{uuid4()}"
    trace_id = f"parsed-trace-{uuid4()}"
    testcase_id = "TC-ROUNDTRIP-001"

    artifact_storage_directory = (
        tmp_path
        / "artifacts"
    )

    async with async_session_factory() as session:
        persisted_artifact = (
            await create_persisted_test_artifact(
                session=session,
                source_path=SAMPLE_TRACE,
                storage_directory=(
                    artifact_storage_directory
                ),
                tenant_id=tenant_id,
                trace_id=trace_id,
                testcase_id=testcase_id,
                correlation_id=str(uuid4()),
                producer="pytest.integration",
            )
        )

        worker = build_parser_worker(
            session=session,
            trace_directory=(
                artifact_storage_directory
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
            persisted_artifact.event,
        )

        await session.commit()

    async with async_session_factory() as session:
        store = ParsedTraceStore(
            session,
        )

        loaded = await store.get_domain(
            tenant_id=tenant_id,
            trace_id=trace_id,
        )

    assert outgoing_event.payload["artifact_id"] == str(
        persisted_artifact.artifact.artifact_id,
    )

    assert loaded is not None

    assert loaded.metadata["tenant_id"] == tenant_id
    assert loaded.metadata["trace_id"] == trace_id
    assert (
        loaded.metadata["testcase_id"]
        == testcase_id
    )

    assert loaded.source.tenant_id == tenant_id
    assert loaded.source.trace_id == trace_id
    assert (
        loaded.source.testcase_id
        == testcase_id
    )

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
