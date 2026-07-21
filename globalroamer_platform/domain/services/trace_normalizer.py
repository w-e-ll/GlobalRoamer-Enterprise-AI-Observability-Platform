from __future__ import annotations

import logging
from typing import Any

from globalroamer_platform.domain.models.operational_event import (
    OperationalEvent,
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


logger = logging.getLogger(__name__)


class TraceNormalizer:
    """
    Convert classified trace evidence into canonical operational events.

    The normalizer is a pure domain service:

    - it does not access the database;
    - it does not publish messages;
    - it does not manage transactions;
    - it does not mutate ParsedTrace;
    - it deterministically converts evidence into OperationalEvent models.

    Application use cases and workers own persistence, event creation,
    transaction boundaries, retries, and logging context.
    """

    def normalize(
        self,
        parsed_trace: ParsedTrace,
    ) -> tuple[OperationalEvent, ...]:
        """Normalize all classified evidence in one parsed trace."""

        if not isinstance(parsed_trace, ParsedTrace):
            raise TypeError(
                "parsed_trace must be a ParsedTrace"
            )

        tenant_id = self._required_metadata_string(
            parsed_trace,
            "tenant_id",
        )
        trace_id = self._required_metadata_string(
            parsed_trace,
            "trace_id",
        )
        testcase_id = self._optional_metadata_string(
            parsed_trace,
            "testcase_id",
        )

        events = tuple(
            self._evidence_to_event(
                parsed_trace=parsed_trace,
                evidence=evidence,
                tenant_id=tenant_id,
                trace_id=trace_id,
                testcase_id=testcase_id,
                sequence_number=index,
            )
            for index, evidence in enumerate(
                parsed_trace.evidences,
                start=1,
            )
        )

        logger.info(
            "Trace normalization completed",
            extra={
                "tenant_id": tenant_id,
                "trace_id": trace_id,
                "testcase_id": testcase_id,
                "evidence_count": (
                    parsed_trace.evidence_count
                ),
                "operational_event_count": len(events),
                "stage": "domain.trace_normalizer",
            },
        )

        return events

    def _evidence_to_event(
        self,
        *,
        parsed_trace: ParsedTrace,
        evidence: ParsedEvidence,
        tenant_id: str,
        trace_id: str,
        testcase_id: str | None,
        sequence_number: int,
    ) -> OperationalEvent:
        event_name = self._event_name(evidence)
        event_family = self._event_family(evidence)
        severity = self._severity(evidence)
        cause = self._cause(evidence)
        result = self._result(evidence)

        operator = self._value_as_optional_string(
            parsed_trace.get_mapped_value(
                "operator",
                parsed_trace.get_extracted_value(
                    "operator",
                ),
            )
        )
        country = self._value_as_optional_string(
            parsed_trace.get_mapped_value(
                "country",
                parsed_trace.get_extracted_value(
                    "country",
                ),
            )
        )

        recommendation = self._recommendation(
            evidence
        )
        retry_recommended = self._retry_recommended(
            evidence
        )

        extracted_values = (
            parsed_trace.extracted_values.to_dict()
        )

        return OperationalEvent.create(
            tenant_id=tenant_id,
            trace_id=trace_id,
            testcase_id=testcase_id,
            sequence_number=sequence_number,
            event_name=event_name,
            event_family=event_family,
            severity=severity,
            raw_message=evidence.source_line,
            normalized_message=self._normalized_message(
                evidence=evidence,
                event_name=event_name,
                operator=operator,
                country=country,
                cause=cause,
            ),
            source_line_number=(
                evidence.source_line_number
            ),
            timestamp=evidence.timestamp,
            protocol_layer=evidence.protocol_layer,
            direction=self._direction(evidence),
            result=result,
            workflow_stage=self._workflow_stage(
                evidence
            ),
            network_domain=self._network_domain(
                evidence
            ),
            operator=operator,
            country=country,
            cause=cause,
            retry_recommended=retry_recommended,
            recommendation=recommendation,
            tags=self._tags(evidence),
            evidence_lines=(
                evidence.source_line,
            ),
            extracted_values=extracted_values,
            metadata={
                "evidence_type": (
                    evidence.evidence_type.value
                ),
                "evidence_category": evidence.category,
                "evidence_value": evidence.value,
                "confidence": evidence.confidence,
                "metric_name": evidence.metric_name,
                "event_code": evidence.event_code,
                "source_line_number": (
                    evidence.source_line_number
                ),
                "source_event": evidence.metadata.get(
                    "event"
                ),
                "source_type": evidence.metadata.get(
                    "type"
                ),
            },
        )

    @staticmethod
    def _event_name(
        evidence: ParsedEvidence,
    ) -> str:
        mapping = {
            "plmn_not_allowed": "PLMN_NOT_ALLOWED",
            "location_update_failed": (
                "LOCATION_UPDATE_FAILED"
            ),
            "location_update_reject": (
                "MM_LOCATION_UPDATE_REJECT"
            ),
            "location_update_request": (
                "MM_LOCATION_UPDATE_REQUEST"
            ),
            "registration_denied": (
                "REGISTRATION_DENIED"
            ),
            "nas_registered": "NAS_REGISTERED",
            "nas_not_registered": (
                "NAS_NOT_REGISTERED"
            ),
            "ps_attached": "PS_ATTACHED",
            "detached": "DETACHED",
            "timeout": "TIMEOUT",
            "retry_detected": "RETRY_DETECTED",
            "failure_signal": "FAILURE_SIGNAL",
            "reject_signal": "REJECT_SIGNAL",
        }

        return mapping.get(
            evidence.category,
            evidence.category.upper(),
        )

    @staticmethod
    def _event_family(
        evidence: ParsedEvidence,
    ) -> OperationalEventFamily:
        mapping = {
            EvidenceType.MOBILITY_MANAGEMENT: (
                OperationalEventFamily.MOBILITY_MANAGEMENT
            ),
            EvidenceType.NETWORK_STATE: (
                OperationalEventFamily.NETWORK_STATE
            ),
            EvidenceType.AUTHENTICATION: (
                OperationalEventFamily.AUTHENTICATION
            ),
            EvidenceType.CONNECTIVITY: (
                OperationalEventFamily.CONNECTIVITY
            ),
            EvidenceType.RETRY: (
                OperationalEventFamily.RETRY
            ),
            EvidenceType.TIMING: (
                OperationalEventFamily.TIMING
            ),
            EvidenceType.FAILURE: (
                OperationalEventFamily.FAILURE
            ),
            EvidenceType.REJECTION: (
                OperationalEventFamily.FAILURE
            ),
            EvidenceType.PROTOCOL: (
                OperationalEventFamily.PROTOCOL
            ),
            EvidenceType.OTHER: (
                OperationalEventFamily.GENERIC
            ),
        }

        return mapping.get(
            evidence.evidence_type,
            OperationalEventFamily.GENERIC,
        )

    @staticmethod
    def _severity(
        evidence: ParsedEvidence,
    ) -> OperationalEventSeverity:
        category_overrides = {
            "plmn_not_allowed": (
                OperationalEventSeverity.HIGH
            ),
            "location_update_failed": (
                OperationalEventSeverity.HIGH
            ),
            "location_update_reject": (
                OperationalEventSeverity.HIGH
            ),
            "registration_denied": (
                OperationalEventSeverity.HIGH
            ),
            "timeout": (
                OperationalEventSeverity.MEDIUM
            ),
            "retry_detected": (
                OperationalEventSeverity.MEDIUM
            ),
            "nas_not_registered": (
                OperationalEventSeverity.MEDIUM
            ),
            "detached": (
                OperationalEventSeverity.MEDIUM
            ),
            "failure_signal": (
                OperationalEventSeverity.MEDIUM
            ),
            "reject_signal": (
                OperationalEventSeverity.MEDIUM
            ),
        }

        override = category_overrides.get(
            evidence.category
        )

        if override is not None:
            return override

        severity_mapping = {
            EvidenceSeverity.INFO: (
                OperationalEventSeverity.INFO
            ),
            EvidenceSeverity.LOW: (
                OperationalEventSeverity.LOW
            ),
            EvidenceSeverity.MEDIUM: (
                OperationalEventSeverity.MEDIUM
            ),
            EvidenceSeverity.HIGH: (
                OperationalEventSeverity.HIGH
            ),
            EvidenceSeverity.CRITICAL: (
                OperationalEventSeverity.CRITICAL
            ),
        }

        return severity_mapping[evidence.severity]

    @staticmethod
    def _cause(
        evidence: ParsedEvidence,
    ) -> str | None:
        mapping = {
            "plmn_not_allowed": "PLMN_NOT_ALLOWED",
            "location_update_failed": (
                "LOCATION_UPDATE_FAILED"
            ),
            "location_update_reject": (
                "LOCATION_UPDATE_REJECT"
            ),
            "registration_denied": (
                "REGISTRATION_DENIED"
            ),
            "timeout": "TIMEOUT",
            "retry_detected": "RETRY",
            "nas_not_registered": (
                "NAS_NOT_REGISTERED"
            ),
            "detached": "DETACHED",
        }

        return mapping.get(evidence.category)

    @staticmethod
    def _workflow_stage(
        evidence: ParsedEvidence,
    ) -> str:
        if evidence.category in {
            "location_update_request",
            "location_update_reject",
            "location_update_failed",
            "plmn_not_allowed",
            "registration_denied",
        }:
            return "mobility_management"

        if evidence.category in {
            "nas_registered",
            "nas_not_registered",
            "ps_attached",
            "detached",
        }:
            return "network_registration"

        if evidence.category in {
            "timeout",
            "retry_detected",
        }:
            return "stability_or_retry"

        if evidence.evidence_type == EvidenceType.AUTHENTICATION:
            return "authentication"

        return "trace_analysis"

    @staticmethod
    def _network_domain(
        evidence: ParsedEvidence,
    ) -> str:
        if evidence.evidence_type in {
            EvidenceType.MOBILITY_MANAGEMENT,
            EvidenceType.NETWORK_STATE,
        }:
            return "roaming"

        if evidence.evidence_type in {
            EvidenceType.CONNECTIVITY,
            EvidenceType.TIMING,
            EvidenceType.RETRY,
        }:
            return "connectivity"

        if evidence.evidence_type == EvidenceType.AUTHENTICATION:
            return "authentication"

        return "unknown"

    @staticmethod
    def _direction(
        evidence: ParsedEvidence,
    ) -> OperationalEventDirection:
        text = evidence.source_line.casefold()

        if (
            "send" in text
            or "sent" in text
            or "-->" in text
        ):
            return OperationalEventDirection.SEND

        if (
            "recv" in text
            or "received" in text
            or "<--" in text
        ):
            return OperationalEventDirection.RECEIVE

        return OperationalEventDirection.UNKNOWN

    @staticmethod
    def _result(
        evidence: ParsedEvidence,
    ) -> OperationalEventResult:
        if evidence.category == "timeout":
            return OperationalEventResult.TIMEOUT

        if evidence.category in {
            "location_update_reject",
            "registration_denied",
            "reject_signal",
            "plmn_not_allowed",
        }:
            return OperationalEventResult.REJECTED

        if evidence.category in {
            "location_update_failed",
            "failure_signal",
            "nas_not_registered",
            "detached",
        }:
            return OperationalEventResult.FAILED

        if evidence.category in {
            "nas_registered",
            "ps_attached",
        }:
            return OperationalEventResult.SUCCESS

        if evidence.category in {
            "location_update_request",
            "retry_detected",
        }:
            return OperationalEventResult.OBSERVED

        if evidence.is_failure:
            return OperationalEventResult.FAILED

        return OperationalEventResult.OBSERVED

    @staticmethod
    def _tags(
        evidence: ParsedEvidence,
    ) -> tuple[str, ...]:
        tags = {
            evidence.evidence_type.value,
            evidence.category,
            evidence.severity.value,
        }

        if evidence.protocol_layer:
            tags.add(
                evidence.protocol_layer
            )

        if evidence.event_code:
            tags.add(
                evidence.event_code
            )

        return tuple(
            sorted(tags)
        )

    @staticmethod
    def _recommendation(
        evidence: ParsedEvidence,
    ) -> str | None:
        if evidence.category == "plmn_not_allowed":
            return (
                "Check HPLMN/VPLMN roaming agreement, SIM profile "
                "and PLMN authorization."
            )

        if evidence.category in {
            "location_update_failed",
            "location_update_reject",
            "registration_denied",
        }:
            return (
                "Review the mobility-management location update flow, "
                "reject cause, operator configuration and roaming "
                "restrictions."
            )

        if evidence.category == "timeout":
            return (
                "Check network stability, timeout thresholds, radio "
                "state and transport delays."
            )

        if evidence.category == "retry_detected":
            return (
                "Compare retry count and timing with successful "
                "historical traces before escalation."
            )

        if evidence.category in {
            "nas_not_registered",
            "detached",
        }:
            return (
                "Check registration state, attach state, radio "
                "availability and network availability."
            )

        return None

    @staticmethod
    def _retry_recommended(
        evidence: ParsedEvidence,
    ) -> bool:
        if evidence.category in {
            "plmn_not_allowed",
            "registration_denied",
            "location_update_reject",
        }:
            return False

        return evidence.category in {
            "timeout",
            "retry_detected",
            "nas_not_registered",
            "detached",
        }

    @staticmethod
    def _normalized_message(
        *,
        evidence: ParsedEvidence,
        event_name: str,
        operator: str | None,
        country: str | None,
        cause: str | None,
    ) -> str:
        normalized_operator = operator or "unknown_operator"
        normalized_country = country or "unknown_country"

        components = [
            f"{event_name} detected",
            f"operator={normalized_operator}",
            f"country={normalized_country}",
        ]

        if cause:
            components.append(
                f"cause={cause}"
            )

        components.append(
            f"value={evidence.value}"
        )

        return ", ".join(components)

    @staticmethod
    def _required_metadata_string(
        parsed_trace: ParsedTrace,
        field_name: str,
    ) -> str:
        value = parsed_trace.metadata.get(
            field_name
        )

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise ValueError(
                "ParsedTrace metadata must contain a "
                f"non-empty {field_name!r} string"
            )

        return value.strip()

    @staticmethod
    def _optional_metadata_string(
        parsed_trace: ParsedTrace,
        field_name: str,
    ) -> str | None:
        value = parsed_trace.metadata.get(
            field_name
        )

        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError(
                "ParsedTrace metadata field "
                f"{field_name!r} must be a string or null"
            )

        normalized_value = value.strip()

        return normalized_value or None

    @staticmethod
    def _value_as_optional_string(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        normalized_value = str(value).strip()

        return normalized_value or None
