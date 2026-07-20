from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class EvidenceType(StrEnum):
    """High-level type of an extracted operational fact."""

    MOBILITY_MANAGEMENT = "mobility_management"
    NETWORK_STATE = "network_state"
    TIMING = "timing"
    RETRY = "retry"
    FAILURE = "failure"
    REJECTION = "rejection"
    AUTHENTICATION = "authentication"
    CONNECTIVITY = "connectivity"
    PROTOCOL = "protocol"
    OTHER = "other"


class EvidenceSeverity(StrEnum):
    """Operational severity assigned during evidence classification."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class ParsedEvidence:
    """
    Represent one classified fact extracted from a raw trace row.

    ParsedEvidence retains a direct reference to the original source
    location so every classification remains explainable and
    auditable.
    """

    evidence_type: EvidenceType
    category: str
    value: str
    confidence: float

    source_line_number: int
    source_line: str

    severity: EvidenceSeverity
    timestamp: datetime | None = None

    protocol_layer: str | None = None
    event_code: str | None = None
    metric_name: str | None = None

    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_type, EvidenceType):
            raise TypeError(
                "evidence_type must be an EvidenceType"
            )

        if not isinstance(self.severity, EvidenceSeverity):
            raise TypeError(
                "severity must be an EvidenceSeverity"
            )

        normalized_category = self.category.strip()

        if not normalized_category:
            raise ValueError(
                "Evidence category must not be empty"
            )

        normalized_value = self.value.strip()

        if not normalized_value:
            raise ValueError(
                "Evidence value must not be empty"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "Evidence confidence must be between 0.0 and 1.0"
            )

        if self.source_line_number <= 0:
            raise ValueError(
                "Evidence source_line_number must be greater than zero"
            )

        normalized_source_line = self.source_line.strip()

        if not normalized_source_line:
            raise ValueError(
                "Evidence source_line must not be empty"
            )

        object.__setattr__(
            self,
            "category",
            normalized_category,
        )
        object.__setattr__(
            self,
            "value",
            normalized_value,
        )
        object.__setattr__(
            self,
            "source_line",
            normalized_source_line,
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
            "event_code",
            _normalize_optional_text(
                self.event_code
            ),
        )
        object.__setattr__(
            self,
            "metric_name",
            _normalize_optional_text(
                self.metric_name
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
        evidence_type: EvidenceType,
        category: str,
        value: str,
        confidence: float,
        source_line_number: int,
        source_line: str,
        severity: EvidenceSeverity,
        timestamp: datetime | None = None,
        protocol_layer: str | None = None,
        event_code: str | None = None,
        metric_name: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ParsedEvidence:
        """Create immutable classified evidence."""

        return cls(
            evidence_type=evidence_type,
            category=category,
            value=value,
            confidence=confidence,
            source_line_number=source_line_number,
            source_line=source_line,
            severity=severity,
            timestamp=timestamp,
            protocol_layer=protocol_layer,
            event_code=event_code,
            metric_name=metric_name,
            metadata=metadata or {},
        )

    @property
    def is_failure(self) -> bool:
        """Return whether the evidence represents a failure condition."""

        return self.evidence_type in {
            EvidenceType.FAILURE,
            EvidenceType.REJECTION,
        }

    @property
    def is_high_severity(self) -> bool:
        """Return whether evidence requires high-priority attention."""

        return self.severity in {
            EvidenceSeverity.HIGH,
            EvidenceSeverity.CRITICAL,
        }

    @property
    def has_protocol_context(self) -> bool:
        """Return whether a protocol layer was identified."""

        return self.protocol_layer is not None

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable representation of the evidence."""

        return {
            "evidence_type": self.evidence_type.value,
            "category": self.category,
            "value": self.value,
            "confidence": self.confidence,
            "source_line_number": self.source_line_number,
            "source_line": self.source_line,
            "severity": self.severity.value,
            "timestamp": (
                self.timestamp.isoformat()
                if self.timestamp is not None
                else None
            ),
            "protocol_layer": self.protocol_layer,
            "event_code": self.event_code,
            "metric_name": self.metric_name,
            "metadata": dict(self.metadata),
        }


def _normalize_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized_value = value.strip()

    return normalized_value or None
