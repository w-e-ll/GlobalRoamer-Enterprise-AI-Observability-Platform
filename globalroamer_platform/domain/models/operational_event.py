from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID, uuid4


class OperationalEventFamily(StrEnum):
    """High-level family of a normalized operational event."""

    MOBILITY_MANAGEMENT = "mobility_management"
    NETWORK_STATE = "network_state"
    AUTHENTICATION = "authentication"
    CONNECTIVITY = "connectivity"
    RETRY = "retry"
    TIMING = "timing"
    FAILURE = "failure"
    PROTOCOL = "protocol"
    GENERIC = "generic"


class OperationalEventSeverity(StrEnum):
    """Severity assigned to a normalized operational event."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OperationalEventDirection(StrEnum):
    """Observed direction of the normalized operation."""

    SEND = "send"
    RECEIVE = "receive"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


class OperationalEventResult(StrEnum):
    """Outcome represented by a normalized operational event."""

    OBSERVED = "observed"
    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class OperationalEvent:
    """
    Canonical operational event produced from parsed trace evidence.

    OperationalEvent is the normalized representation consumed by later
    processing stages such as:

    - trace chunking;
    - embeddings generation;
    - similarity search;
    - root-cause analysis;
    - operational reporting.

    The model retains source-line information and evidence metadata so the
    normalized event remains explainable and auditable.
    """

    id: UUID

    tenant_id: str
    trace_id: str
    testcase_id: str | None

    sequence_number: int

    event_name: str
    event_family: OperationalEventFamily
    severity: OperationalEventSeverity

    raw_message: str
    normalized_message: str

    source_line_number: int
    timestamp: datetime | None = None

    protocol_layer: str | None = None
    direction: OperationalEventDirection = (
        OperationalEventDirection.UNKNOWN
    )
    result: OperationalEventResult = OperationalEventResult.UNKNOWN

    workflow_stage: str | None = None
    network_domain: str | None = None

    operator: str | None = None
    country: str | None = None
    cause: str | None = None

    retry_recommended: bool = False
    recommendation: str | None = None

    tags: tuple[str, ...] = ()
    evidence_lines: tuple[str, ...] = ()

    extracted_values: Mapping[str, Any] = MappingProxyType({})
    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("id must be a UUID")

        if not isinstance(
            self.event_family,
            OperationalEventFamily,
        ):
            raise TypeError(
                "event_family must be an OperationalEventFamily"
            )

        if not isinstance(
            self.severity,
            OperationalEventSeverity,
        ):
            raise TypeError(
                "severity must be an OperationalEventSeverity"
            )

        if not isinstance(
            self.direction,
            OperationalEventDirection,
        ):
            raise TypeError(
                "direction must be an OperationalEventDirection"
            )

        if not isinstance(
            self.result,
            OperationalEventResult,
        ):
            raise TypeError(
                "result must be an OperationalEventResult"
            )

        tenant_id = _required_text(
            self.tenant_id,
            field_name="tenant_id",
        )
        trace_id = _required_text(
            self.trace_id,
            field_name="trace_id",
        )
        event_name = _required_text(
            self.event_name,
            field_name="event_name",
        )
        raw_message = _required_text(
            self.raw_message,
            field_name="raw_message",
        )
        normalized_message = _required_text(
            self.normalized_message,
            field_name="normalized_message",
        )

        testcase_id = _normalize_optional_text(
            self.testcase_id
        )

        if self.sequence_number <= 0:
            raise ValueError(
                "sequence_number must be greater than zero"
            )

        if self.source_line_number <= 0:
            raise ValueError(
                "source_line_number must be greater than zero"
            )

        normalized_tags = _normalize_tags(
            self.tags
        )
        normalized_evidence_lines = _normalize_messages(
            self.evidence_lines
        )

        object.__setattr__(
            self,
            "tenant_id",
            tenant_id,
        )
        object.__setattr__(
            self,
            "trace_id",
            trace_id,
        )
        object.__setattr__(
            self,
            "testcase_id",
            testcase_id,
        )
        object.__setattr__(
            self,
            "event_name",
            event_name.upper(),
        )
        object.__setattr__(
            self,
            "raw_message",
            raw_message,
        )
        object.__setattr__(
            self,
            "normalized_message",
            normalized_message,
        )
        object.__setattr__(
            self,
            "protocol_layer",
            _normalize_optional_text(
                self.protocol_layer
            ),
        )
        object.__setattr__(
            self,
            "workflow_stage",
            _normalize_optional_text(
                self.workflow_stage
            ),
        )
        object.__setattr__(
            self,
            "network_domain",
            _normalize_optional_text(
                self.network_domain
            ),
        )
        object.__setattr__(
            self,
            "operator",
            _normalize_optional_text(
                self.operator
            ),
        )
        object.__setattr__(
            self,
            "country",
            _normalize_optional_text(
                self.country
            ),
        )
        object.__setattr__(
            self,
            "cause",
            _normalize_optional_text(
                self.cause
            ),
        )
        object.__setattr__(
            self,
            "recommendation",
            _normalize_optional_text(
                self.recommendation
            ),
        )
        object.__setattr__(
            self,
            "tags",
            normalized_tags,
        )
        object.__setattr__(
            self,
            "evidence_lines",
            normalized_evidence_lines,
        )
        object.__setattr__(
            self,
            "extracted_values",
            MappingProxyType(
                dict(self.extracted_values)
            ),
        )
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(
                dict(self.metadata)
            ),
        )

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        trace_id: str,
        testcase_id: str | None,
        sequence_number: int,
        event_name: str,
        event_family: OperationalEventFamily,
        severity: OperationalEventSeverity,
        raw_message: str,
        normalized_message: str,
        source_line_number: int,
        timestamp: datetime | None = None,
        protocol_layer: str | None = None,
        direction: OperationalEventDirection = (
            OperationalEventDirection.UNKNOWN
        ),
        result: OperationalEventResult = (
            OperationalEventResult.UNKNOWN
        ),
        workflow_stage: str | None = None,
        network_domain: str | None = None,
        operator: str | None = None,
        country: str | None = None,
        cause: str | None = None,
        retry_recommended: bool = False,
        recommendation: str | None = None,
        tags: tuple[str, ...] = (),
        evidence_lines: tuple[str, ...] = (),
        extracted_values: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> OperationalEvent:
        """Create an immutable normalized operational event."""

        return cls(
            id=uuid4(),
            tenant_id=tenant_id,
            trace_id=trace_id,
            testcase_id=testcase_id,
            sequence_number=sequence_number,
            event_name=event_name,
            event_family=event_family,
            severity=severity,
            raw_message=raw_message,
            normalized_message=normalized_message,
            source_line_number=source_line_number,
            timestamp=timestamp,
            protocol_layer=protocol_layer,
            direction=direction,
            result=result,
            workflow_stage=workflow_stage,
            network_domain=network_domain,
            operator=operator,
            country=country,
            cause=cause,
            retry_recommended=retry_recommended,
            recommendation=recommendation,
            tags=tags,
            evidence_lines=evidence_lines,
            extracted_values=extracted_values or {},
            metadata=metadata or {},
        )

    @property
    def is_failure(self) -> bool:
        """Return whether the event represents an unsuccessful result."""

        return self.result in {
            OperationalEventResult.FAILED,
            OperationalEventResult.REJECTED,
            OperationalEventResult.TIMEOUT,
        }

    @property
    def is_high_severity(self) -> bool:
        """Return whether the event requires high-priority attention."""

        return self.severity in {
            OperationalEventSeverity.HIGH,
            OperationalEventSeverity.CRITICAL,
        }

    @property
    def requires_attention(self) -> bool:
        """Return whether the event should be highlighted operationally."""

        return self.is_failure or self.is_high_severity

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable representation of the event."""

        return {
            "id": str(self.id),
            "tenant_id": self.tenant_id,
            "trace_id": self.trace_id,
            "testcase_id": self.testcase_id,
            "sequence_number": self.sequence_number,
            "event_name": self.event_name,
            "event_family": self.event_family.value,
            "severity": self.severity.value,
            "raw_message": self.raw_message,
            "normalized_message": self.normalized_message,
            "source_line_number": self.source_line_number,
            "timestamp": (
                self.timestamp.isoformat()
                if self.timestamp is not None
                else None
            ),
            "protocol_layer": self.protocol_layer,
            "direction": self.direction.value,
            "result": self.result.value,
            "workflow_stage": self.workflow_stage,
            "network_domain": self.network_domain,
            "operator": self.operator,
            "country": self.country,
            "cause": self.cause,
            "retry_recommended": self.retry_recommended,
            "recommendation": self.recommendation,
            "tags": list(self.tags),
            "evidence_lines": list(
                self.evidence_lines
            ),
            "extracted_values": dict(
                self.extracted_values
            ),
            "metadata": dict(self.metadata),
        }


def _required_text(
    value: str,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a string"
        )

    normalized_value = value.strip()

    if not normalized_value:
        raise ValueError(
            f"{field_name} must not be empty"
        )

    return normalized_value


def _normalize_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise TypeError(
            "Optional text values must be strings or None"
        )

    normalized_value = value.strip()

    return normalized_value or None


def _normalize_tags(
    tags: tuple[str, ...],
) -> tuple[str, ...]:
    normalized_tags: set[str] = set()

    for tag in tags:
        if not isinstance(tag, str):
            raise TypeError(
                "tags must contain strings"
            )

        normalized_tag = tag.strip().casefold()

        if normalized_tag:
            normalized_tags.add(
                normalized_tag
            )

    return tuple(
        sorted(normalized_tags)
    )


def _normalize_messages(
    messages: tuple[str, ...],
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()

    for message in messages:
        if not isinstance(message, str):
            raise TypeError(
                "evidence_lines must contain strings"
            )

        normalized_message = message.strip()

        if (
            not normalized_message
            or normalized_message in seen
        ):
            continue

        seen.add(normalized_message)
        result.append(normalized_message)

    return tuple(result)
