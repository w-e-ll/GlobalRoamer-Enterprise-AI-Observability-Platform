from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

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
from globalroamer_platform.infrastructure.persistence.operational_event_store import (
    OperationalEventStore,
)


def build_operational_event(
    *,
    tenant_id: str,
    trace_id: str,
    sequence_number: int,
    source_line_number: int,
) -> OperationalEvent:
    """Create a complete OperationalEvent for persistence tests."""

    return OperationalEvent.create(
        tenant_id=tenant_id,
        trace_id=trace_id,
        testcase_id="TC-OPERATIONAL-EVENT-001",
        sequence_number=sequence_number,
        event_name="authentication_request",
        event_family=OperationalEventFamily.AUTHENTICATION,
        severity=OperationalEventSeverity.MEDIUM,
        raw_message=(
            f"Authentication request on source line "
            f"{source_line_number}"
        ),
        normalized_message="Authentication request observed",
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
            f"line {source_line_number}: authentication request",
        ),
        extracted_values={
            "imsi": "206010000000001",
            "protocol": "NAS",
        },
        metadata={
            "source": "pytest",
            "parser_version": "1.0",
        },
    )


@pytest.mark.asyncio
async def test_save_and_get_by_id_round_trip() -> None:
    """
    OperationalEvent survives a PostgreSQL persistence round trip.

    The event is saved and committed in one session and reconstructed through
    OperationalEventStore in a new session.
    """

    tenant_id = f"operational-event-store-{uuid4()}"
    trace_id = f"operational-trace-{uuid4()}"

    original = build_operational_event(
        tenant_id=tenant_id,
        trace_id=trace_id,
        sequence_number=1,
        source_line_number=10,
    )

    async with async_session_factory() as session:
        store = OperationalEventStore(session)

        await store.save(original)
        await session.commit()

    async with async_session_factory() as session:
        store = OperationalEventStore(session)

        loaded = await store.get_by_id(original.id)

    assert loaded is not None

    assert loaded.id == original.id
    assert loaded.tenant_id == tenant_id
    assert loaded.trace_id == trace_id
    assert loaded.testcase_id == original.testcase_id

    assert loaded.sequence_number == 1
    assert loaded.source_line_number == 10

    assert loaded.event_name == "AUTHENTICATION_REQUEST"
    assert loaded.event_family is OperationalEventFamily.AUTHENTICATION
    assert loaded.severity is OperationalEventSeverity.MEDIUM
    assert loaded.direction is OperationalEventDirection.SEND
    assert loaded.result is OperationalEventResult.OBSERVED

    assert loaded.raw_message == original.raw_message
    assert loaded.normalized_message == original.normalized_message
    assert loaded.timestamp == original.timestamp

    assert loaded.protocol_layer == "NAS"
    assert loaded.workflow_stage == "authentication"
    assert loaded.network_domain == "mobile_core"
    assert loaded.operator == "Test Operator"
    assert loaded.country == "Belgium"

    assert loaded.retry_recommended is False
    assert loaded.recommendation == "Continue processing the trace"

    assert loaded.tags == (
        "authentication",
        "nas",
    )
    assert loaded.evidence_lines == (
        "line 10: authentication request",
    )

    assert dict(loaded.extracted_values) == {
        "imsi": "206010000000001",
        "protocol": "NAS",
    }
    assert dict(loaded.metadata) == {
        "source": "pytest",
        "parser_version": "1.0",
    }


@pytest.mark.asyncio
async def test_save_many_and_list_by_trace_returns_ordered_events() -> None:
    """
    Events belonging to a tenant trace are returned in deterministic order.

    Events are deliberately inserted out of order to verify that the store
    orders them by sequence number, source line number, and UUID.
    """

    tenant_id = f"operational-event-list-{uuid4()}"
    trace_id = f"operational-trace-{uuid4()}"

    third = build_operational_event(
        tenant_id=tenant_id,
        trace_id=trace_id,
        sequence_number=3,
        source_line_number=30,
    )
    first = build_operational_event(
        tenant_id=tenant_id,
        trace_id=trace_id,
        sequence_number=1,
        source_line_number=10,
    )
    second = build_operational_event(
        tenant_id=tenant_id,
        trace_id=trace_id,
        sequence_number=2,
        source_line_number=20,
    )

    async with async_session_factory() as session:
        store = OperationalEventStore(session)

        await store.save_many(
            (
                third,
                first,
                second,
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        store = OperationalEventStore(session)

        loaded = await store.list_by_trace(
            tenant_id=tenant_id,
            trace_id=trace_id,
        )

    assert len(loaded) == 3

    assert tuple(
        event.sequence_number
        for event in loaded
    ) == (
        1,
        2,
        3,
    )

    assert tuple(
        event.source_line_number
        for event in loaded
    ) == (
        10,
        20,
        30,
    )

    assert tuple(
        event.id
        for event in loaded
    ) == (
        first.id,
        second.id,
        third.id,
    )
