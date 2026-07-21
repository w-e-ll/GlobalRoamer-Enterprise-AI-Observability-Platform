from datetime import datetime, timezone

from globalroamer_platform.domain.models.extracted_trace_values import (
    ExtractedTraceValues,
    ExtractedValue,
)
from globalroamer_platform.domain.models.mapped_trace_values import (
    MappedTraceValues,
)
from globalroamer_platform.domain.models.operational_event import (
    OperationalEventDirection,
    OperationalEventFamily,
    OperationalEventResult,
    OperationalEventSeverity,
)
from globalroamer_platform.domain.models.parsed_evidence import (
    EvidenceSeverity,
    EvidenceType,
    ParsedEvidence,
)
from globalroamer_platform.domain.models.parsed_trace import (
    ParsedTrace,
)
from globalroamer_platform.domain.models.raw_trace import (
    RawTrace,
)
from globalroamer_platform.domain.models.source_artifact import (
    SourceArtifact,
    SourceArtifactType,
)
from globalroamer_platform.domain.services.trace_normalizer import (
    TraceNormalizer,
)


def test_normalizes_parsed_evidence_into_operational_event() -> None:
    source = SourceArtifact(
        id=__import__("uuid").uuid4(),
        artifact_type=SourceArtifactType.TRACE,
        source_path=__import__("pathlib").Path(
            "/tmp/trace.csv"
        ),
        filename="trace.csv",
        extension=".csv",
        size_bytes=128,
        checksum_sha256="a" * 64,
        loaded_at=datetime.now(timezone.utc),
        content_type="text/csv",
        tenant_id="bics",
        trace_id="trace-001",
        testcase_id="TC-001",
    )

    raw_trace = RawTrace(
        source=source,
        rows=(),
        delimiter=",",
        encoding="utf-8",
        parser_warnings=(),
    )

    extracted_values = ExtractedTraceValues.create(
        values={
            "operator": ExtractedValue(
                name="operator",
                value="Orange",
                source_line_number=1,
                extraction_method="test",
            ),
            "country": ExtractedValue(
                name="country",
                value="France",
                source_line_number=1,
                extraction_method="test",
            ),
        },
    )

    mapped_values = MappedTraceValues(
        values={},
        mapping_warnings=(),
        mapping_errors=(),
    )

    evidence = ParsedEvidence.create(
        evidence_type=(
            EvidenceType.MOBILITY_MANAGEMENT
        ),
        category="location_update_reject",
        value="13",
        confidence=0.98,
        source_line_number=7,
        source_line=(
            "recv <-- Location Update Reject cause=13"
        ),
        severity=EvidenceSeverity.HIGH,
        timestamp=datetime(
            2026,
            7,
            21,
            12,
            30,
            tzinfo=timezone.utc,
        ),
        protocol_layer="MM",
        event_code="13",
    )

    parsed_trace = ParsedTrace.create(
        raw_trace=raw_trace,
        extracted_values=extracted_values,
        mapped_values=mapped_values,
        evidences=(evidence,),
        metadata={
            "tenant_id": "bics",
            "trace_id": "trace-001",
            "testcase_id": "TC-001",
        },
    )

    normalizer = TraceNormalizer()

    result = normalizer.normalize(
        parsed_trace
    )

    assert len(result) == 1

    event = result[0]

    assert event.tenant_id == "bics"
    assert event.trace_id == "trace-001"
    assert event.testcase_id == "TC-001"
    assert event.sequence_number == 1

    assert event.event_name == (
        "MM_LOCATION_UPDATE_REJECT"
    )
    assert event.event_family == (
        OperationalEventFamily.MOBILITY_MANAGEMENT
    )
    assert event.severity == (
        OperationalEventSeverity.HIGH
    )
    assert event.direction == (
        OperationalEventDirection.RECEIVE
    )
    assert event.result == (
        OperationalEventResult.REJECTED
    )

    assert event.cause == (
        "LOCATION_UPDATE_REJECT"
    )
    assert event.retry_recommended is False
    assert event.operator == "Orange"
    assert event.country == "France"

    assert event.source_line_number == 7
    assert event.raw_message == (
        "recv <-- Location Update Reject cause=13"
    )

    assert (
        "MM_LOCATION_UPDATE_REJECT detected"
        in event.normalized_message
    )
    assert "operator=Orange" in (
        event.normalized_message
    )
    assert "country=France" in (
        event.normalized_message
    )
    assert "cause=LOCATION_UPDATE_REJECT" in (
        event.normalized_message
    )


def test_returns_empty_tuple_when_trace_has_no_evidence() -> None:
    source = SourceArtifact(
        id=__import__("uuid").uuid4(),
        artifact_type=SourceArtifactType.TRACE,
        source_path=__import__("pathlib").Path(
            "/tmp/empty.csv"
        ),
        filename="empty.csv",
        extension=".csv",
        size_bytes=0,
        checksum_sha256="b" * 64,
        loaded_at=datetime.now(timezone.utc),
        content_type="text/csv",
        tenant_id="bics",
        trace_id="trace-empty",
        testcase_id=None,
    )

    parsed_trace = ParsedTrace.create(
        raw_trace=RawTrace(
            source=source,
            rows=(),
            delimiter=",",
            encoding="utf-8",
            parser_warnings=(),
        ),
        extracted_values=ExtractedTraceValues.empty(),
        mapped_values=MappedTraceValues(
            values={},
            mapping_warnings=(),
            mapping_errors=(),
        ),
        metadata={
            "tenant_id": "bics",
            "trace_id": "trace-empty",
            "testcase_id": None,
        },
    )

    result = TraceNormalizer().normalize(
        parsed_trace
    )

    assert result == ()
