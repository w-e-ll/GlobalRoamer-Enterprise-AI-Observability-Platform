from __future__ import annotations

from dataclasses import replace
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
from globalroamer_platform.infrastructure.models.operational_event import (
    OperationalEventModel,
)
from globalroamer_platform.infrastructure.persistence.operational_event_mapper import (
    OperationalEventMapper,
)


def build_operational_event() -> OperationalEvent:
    return OperationalEvent(
        id=uuid4(),
        tenant_id="tenant-001",
        trace_id="trace-001",
        testcase_id="TC-001",
        sequence_number=1,
        event_name="location_update_failed",
        event_family=(
            OperationalEventFamily.MOBILITY_MANAGEMENT
        ),
        severity=OperationalEventSeverity.HIGH,
        raw_message="Location update failed",
        normalized_message=(
            "LOCATION_UPDATE_FAILED for operator A"
        ),
        source_line_number=42,
        timestamp=datetime(
            2026,
            7,
            21,
            12,
            30,
            tzinfo=timezone.utc,
        ),
        protocol_layer="NAS",
        direction=OperationalEventDirection.RECEIVE,
        result=OperationalEventResult.FAILED,
        workflow_stage="registration",
        network_domain="mobile",
        operator="Operator A",
        country="Belgium",
        cause="PLMN not allowed",
        retry_recommended=True,
        recommendation="Retry on another network",
        tags=(
            "mobility",
            "registration",
        ),
        evidence_lines=(
            "line one",
            "line two",
        ),
        extracted_values={
            "mcc": "206",
            "mnc": "01",
        },
        metadata={
            "confidence": 0.98,
            "source": "trace",
        },
    )


def test_to_model_maps_all_fields() -> None:
    event = build_operational_event()

    model = OperationalEventMapper.to_model(
        event
    )

    assert isinstance(
        model,
        OperationalEventModel,
    )

    assert model.id == event.id
    assert model.tenant_id == event.tenant_id
    assert model.trace_id == event.trace_id
    assert model.testcase_id == event.testcase_id
    assert (
        model.sequence_number
        == event.sequence_number
    )
    assert model.event_name == event.event_name
    assert (
        model.event_family
        == event.event_family.value
    )
    assert model.severity == event.severity.value
    assert model.raw_message == event.raw_message
    assert (
        model.normalized_message
        == event.normalized_message
    )
    assert (
        model.source_line_number
        == event.source_line_number
    )
    assert model.timestamp == event.timestamp
    assert (
        model.protocol_layer
        == event.protocol_layer
    )
    assert model.direction == event.direction.value
    assert model.result == event.result.value
    assert (
        model.workflow_stage
        == event.workflow_stage
    )
    assert (
        model.network_domain
        == event.network_domain
    )
    assert model.operator == event.operator
    assert model.country == event.country
    assert model.cause == event.cause
    assert (
        model.retry_recommended
        == event.retry_recommended
    )
    assert (
        model.recommendation
        == event.recommendation
    )
    assert model.tags == list(event.tags)
    assert model.evidence_lines == list(
        event.evidence_lines
    )
    assert model.extracted_values == dict(
        event.extracted_values
    )
    assert model.event_metadata == dict(
        event.metadata
    )


def test_to_domain_reconstructs_event() -> None:
    original = build_operational_event()

    model = OperationalEventMapper.to_model(
        original
    )

    restored = OperationalEventMapper.to_domain(
        model
    )

    assert restored == original
    assert isinstance(
        restored.event_family,
        OperationalEventFamily,
    )
    assert isinstance(
        restored.severity,
        OperationalEventSeverity,
    )
    assert isinstance(
        restored.direction,
        OperationalEventDirection,
    )
    assert isinstance(
        restored.result,
        OperationalEventResult,
    )


def test_round_trip_preserves_immutable_collections() -> None:
    original = build_operational_event()

    restored = OperationalEventMapper.to_domain(
        OperationalEventMapper.to_model(
            original
        )
    )

    assert isinstance(restored.tags, tuple)
    assert isinstance(
        restored.evidence_lines,
        tuple,
    )
    assert dict(restored.extracted_values) == {
        "mcc": "206",
        "mnc": "01",
    }
    assert dict(restored.metadata) == {
        "confidence": 0.98,
        "source": "trace",
    }


def test_to_model_accepts_nullable_optional_fields() -> None:
    event = OperationalEvent(
        id=uuid4(),
        tenant_id="tenant-001",
        trace_id="trace-001",
        testcase_id=None,
        sequence_number=1,
        event_name="generic_event",
        event_family=(
            OperationalEventFamily.GENERIC
        ),
        severity=OperationalEventSeverity.INFO,
        raw_message="Observed event",
        normalized_message="Observed event",
        source_line_number=1,
    )

    model = OperationalEventMapper.to_model(
        event
    )

    restored = OperationalEventMapper.to_domain(
        model
    )

    assert restored.testcase_id is None
    assert restored.timestamp is None
    assert restored.protocol_layer is None
    assert restored.workflow_stage is None
    assert restored.network_domain is None
    assert restored.operator is None
    assert restored.country is None
    assert restored.cause is None
    assert restored.recommendation is None
    assert restored.tags == ()
    assert restored.evidence_lines == ()
    assert dict(restored.extracted_values) == {}
    assert dict(restored.metadata) == {}


def test_to_models_maps_tuple() -> None:
    first = build_operational_event()

    second = replace(
        first,
        id=uuid4(),
        sequence_number=2,
    )

    models = OperationalEventMapper.to_models(
        (
            first,
            second,
        )
    )

    assert len(models) == 2
    assert models[0].id == first.id
    assert models[1].id == second.id


def test_to_domains_maps_tuple() -> None:
    first = build_operational_event()

    second = replace(
        first,
        id=uuid4(),
        sequence_number=2,
    )

    models = OperationalEventMapper.to_models(
        (
            first,
            second,
        )
    )

    events = OperationalEventMapper.to_domains(
        models
    )

    assert events == (
        first,
        second,
    )


def test_to_model_rejects_invalid_type() -> None:
    with pytest.raises(
        TypeError,
        match="event must be an OperationalEvent",
    ):
        OperationalEventMapper.to_model(
            object()
        )


def test_to_domain_rejects_invalid_type() -> None:
    with pytest.raises(
        TypeError,
        match=(
            "model must be an "
            "OperationalEventModel"
        ),
    ):
        OperationalEventMapper.to_domain(
            object()
        )


def test_to_models_requires_tuple() -> None:
    with pytest.raises(
        TypeError,
        match="events must be a tuple",
    ):
        OperationalEventMapper.to_models(
            []
        )


def test_to_domains_requires_tuple() -> None:
    with pytest.raises(
        TypeError,
        match="models must be a tuple",
    ):
        OperationalEventMapper.to_domains(
            []
        )
