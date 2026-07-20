from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from globalroamer_platform.domain.models.parsed_evidence import (
    EvidenceSeverity,
    EvidenceType,
    ParsedEvidence,
)
from globalroamer_platform.domain.models.raw_trace import (
    RawTrace,
    RawTraceRow,
)


EvidenceFactory = Callable[
    [RawTraceRow],
    ParsedEvidence,
]


@dataclass(frozen=True, slots=True)
class EvidenceRule:
    """
    Describe one deterministic evidence-classification rule.

    All keywords in ``all_keywords`` must occur in the information
    field. At least one keyword in ``any_keywords`` must occur when
    that collection is not empty.
    """

    name: str
    factory: EvidenceFactory

    all_keywords: tuple[str, ...] = ()
    any_keywords: tuple[str, ...] = ()
    excluded_keywords: tuple[str, ...] = ()

    def matches(
        self,
        normalized_information: str,
    ) -> bool:
        if self.excluded_keywords and any(
            keyword in normalized_information
            for keyword in self.excluded_keywords
        ):
            return False

        if self.all_keywords and not all(
            keyword in normalized_information
            for keyword in self.all_keywords
        ):
            return False

        if self.any_keywords and not any(
            keyword in normalized_information
            for keyword in self.any_keywords
        ):
            return False

        return bool(
            self.all_keywords
            or self.any_keywords
        )


class EvidenceExtractor:
    """
    Extract classified operational evidence from a structurally parsed trace.

    The extractor contains deterministic telecom-domain rules. It does
    not read source files, parse CSV, apply external mappings, normalize
    an entire trace, or perform AI inference.

    Rule order is significant: specific telecom patterns must appear
    before generic failure and rejection rules.
    """

    def __init__(
        self,
        *,
        include_generic_rules: bool = True,
    ) -> None:
        self._include_generic_rules = include_generic_rules
        self._rules = self._build_rules(
            include_generic_rules=include_generic_rules
        )

    @property
    def include_generic_rules(self) -> bool:
        return self._include_generic_rules

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    def extract(
        self,
        trace: RawTrace,
    ) -> tuple[ParsedEvidence, ...]:
        """Extract at most one highest-priority evidence item per row."""

        evidences: list[ParsedEvidence] = []

        for row in trace.rows:
            evidence = self.extract_from_row(row)

            if evidence is not None:
                evidences.append(evidence)

        return tuple(evidences)

    def extract_from_row(
        self,
        row: RawTraceRow,
    ) -> ParsedEvidence | None:
        """Classify one raw trace row using ordered deterministic rules."""

        information = row.information

        if information is None:
            return None

        normalized_information = self._normalize_for_matching(
            information
        )

        if not normalized_information:
            return None

        for rule in self._rules:
            if rule.matches(normalized_information):
                return rule.factory(row)

        return None

    @classmethod
    def _build_rules(
        cls,
        *,
        include_generic_rules: bool,
    ) -> tuple[EvidenceRule, ...]:
        rules: list[EvidenceRule] = [
            EvidenceRule(
                name="plmn_not_allowed",
                any_keywords=(
                    "plmn not allowed",
                ),
                factory=cls._build_plmn_not_allowed,
            ),
            EvidenceRule(
                name="location_update_failed",
                any_keywords=(
                    "locationupdate failed",
                    "location update failed",
                ),
                factory=cls._build_location_update_failed,
            ),
            EvidenceRule(
                name="location_update_reject",
                any_keywords=(
                    "mm location updating reject",
                    "mm location update reject",
                ),
                factory=cls._build_location_update_reject,
            ),
            EvidenceRule(
                name="location_update_request",
                any_keywords=(
                    "mm location updating request",
                    "mm location update request",
                ),
                factory=cls._build_location_update_request,
            ),
            EvidenceRule(
                name="registration_denied",
                any_keywords=(
                    "registration denied",
                ),
                factory=cls._build_registration_denied,
            ),
            # The negative NAS rule must be evaluated before the
            # positive rule because "nasnotregistered" contains the
            # substring "nasregistered" only in some loosely formatted
            # source variants.
            EvidenceRule(
                name="nas_not_registered",
                any_keywords=(
                    "nasnotregistered",
                    "registrationstate nasnotregistered",
                    "nas not registered",
                ),
                factory=cls._build_nas_not_registered,
            ),
            EvidenceRule(
                name="nas_registered",
                any_keywords=(
                    "nasregistered",
                    "registrationstate nasregistered",
                    "nas registered",
                ),
                excluded_keywords=(
                    "nasnotregistered",
                    "nas not registered",
                ),
                factory=cls._build_nas_registered,
            ),
            # Detached must be evaluated before attached to avoid
            # ambiguous lines and broad substring matching.
            EvidenceRule(
                name="ps_detached",
                any_keywords=(
                    "psattachstate detached",
                    "psdetached",
                    "ps detached",
                ),
                factory=cls._build_ps_detached,
            ),
            EvidenceRule(
                name="ps_attached",
                any_keywords=(
                    "psattachstate attached",
                    "psattached",
                    "ps attached",
                ),
                excluded_keywords=(
                    "psattachstate detached",
                    "psdetached",
                    "ps detached",
                ),
                factory=cls._build_ps_attached,
            ),
            EvidenceRule(
                name="timeout",
                any_keywords=(
                    "timeout",
                    "timed out",
                ),
                factory=cls._build_timeout,
            ),
            EvidenceRule(
                name="retry",
                any_keywords=(
                    "retry",
                    "retried",
                    "retransmission",
                    "retransmit",
                ),
                factory=cls._build_retry,
            ),
        ]

        if include_generic_rules:
            rules.extend(
                (
                    EvidenceRule(
                        name="generic_failure",
                        any_keywords=(
                            "fail",
                            "failed",
                            "failure",
                            "error",
                            "exception",
                        ),
                        factory=cls._build_generic_failure,
                    ),
                    EvidenceRule(
                        name="generic_rejection",
                        any_keywords=(
                            "reject",
                            "rejected",
                            "denied",
                        ),
                        factory=cls._build_generic_rejection,
                    ),
                )
            )

        return tuple(rules)

    @classmethod
    def _build_plmn_not_allowed(
        cls,
        row: RawTraceRow,
    ) -> ParsedEvidence:
        return cls._create_evidence(
            row=row,
            evidence_type=EvidenceType.MOBILITY_MANAGEMENT,
            category="plmn_not_allowed",
            value="PLMN not allowed",
            confidence=0.98,
            severity=EvidenceSeverity.HIGH,
            protocol_layer="MM",
            event_code="11",
        )

    @classmethod
    def _build_location_update_failed(
        cls,
        row: RawTraceRow,
    ) -> ParsedEvidence:
        return cls._create_evidence(
            row=row,
            evidence_type=EvidenceType.MOBILITY_MANAGEMENT,
            category="location_update_failed",
            value=cls._extract_error_value(
                row.information
            ),
            confidence=0.95,
            severity=EvidenceSeverity.HIGH,
            protocol_layer="MM",
        )

    @classmethod
    def _build_location_update_reject(
        cls,
        row: RawTraceRow,
    ) -> ParsedEvidence:
        return cls._create_evidence(
            row=row,
            evidence_type=EvidenceType.MOBILITY_MANAGEMENT,
            category="location_update_reject",
            value="MM Location updating reject",
            confidence=0.95,
            severity=EvidenceSeverity.HIGH,
            protocol_layer="MM",
        )

    @classmethod
    def _build_location_update_request(
        cls,
        row: RawTraceRow,
    ) -> ParsedEvidence:
        return cls._create_evidence(
            row=row,
            evidence_type=EvidenceType.MOBILITY_MANAGEMENT,
            category="location_update_request",
            value="MM Location updating request",
            confidence=0.90,
            severity=EvidenceSeverity.INFO,
            protocol_layer="MM",
        )

    @classmethod
    def _build_registration_denied(
        cls,
        row: RawTraceRow,
    ) -> ParsedEvidence:
        return cls._create_evidence(
            row=row,
            evidence_type=EvidenceType.MOBILITY_MANAGEMENT,
            category="registration_denied",
            value="Registration denied",
            confidence=0.95,
            severity=EvidenceSeverity.HIGH,
            protocol_layer="MM",
        )

    @classmethod
    def _build_nas_registered(
        cls,
        row: RawTraceRow,
    ) -> ParsedEvidence:
        return cls._create_evidence(
            row=row,
            evidence_type=EvidenceType.NETWORK_STATE,
            category="nas_registered",
            value="NASRegistered",
            confidence=0.85,
            severity=EvidenceSeverity.INFO,
            protocol_layer="NAS",
        )

    @classmethod
    def _build_nas_not_registered(
        cls,
        row: RawTraceRow,
    ) -> ParsedEvidence:
        return cls._create_evidence(
            row=row,
            evidence_type=EvidenceType.NETWORK_STATE,
            category="nas_not_registered",
            value="NASNotRegistered",
            confidence=0.90,
            severity=EvidenceSeverity.MEDIUM,
            protocol_layer="NAS",
        )

    @classmethod
    def _build_ps_attached(
        cls,
        row: RawTraceRow,
    ) -> ParsedEvidence:
        return cls._create_evidence(
            row=row,
            evidence_type=EvidenceType.NETWORK_STATE,
            category="ps_attached",
            value="PSAttached",
            confidence=0.85,
            severity=EvidenceSeverity.INFO,
            protocol_layer="NAS",
        )

    @classmethod
    def _build_ps_detached(
        cls,
        row: RawTraceRow,
    ) -> ParsedEvidence:
        return cls._create_evidence(
            row=row,
            evidence_type=EvidenceType.NETWORK_STATE,
            category="ps_detached",
            value="PSDetached",
            confidence=0.80,
            severity=EvidenceSeverity.MEDIUM,
            protocol_layer="NAS",
        )

    @classmethod
    def _build_timeout(
        cls,
        row: RawTraceRow,
    ) -> ParsedEvidence:
        return cls._create_evidence(
            row=row,
            evidence_type=EvidenceType.TIMING,
            category="timeout",
            value="Timeout",
            confidence=0.85,
            severity=EvidenceSeverity.MEDIUM,
            metric_name="timeout",
        )

    @classmethod
    def _build_retry(
        cls,
        row: RawTraceRow,
    ) -> ParsedEvidence:
        return cls._create_evidence(
            row=row,
            evidence_type=EvidenceType.RETRY,
            category="retry_detected",
            value="Retry",
            confidence=0.80,
            severity=EvidenceSeverity.MEDIUM,
            metric_name="retry_count",
        )

    @classmethod
    def _build_generic_failure(
        cls,
        row: RawTraceRow,
    ) -> ParsedEvidence:
        return cls._create_evidence(
            row=row,
            evidence_type=EvidenceType.FAILURE,
            category="failure_signal",
            value=cls._extract_error_value(
                row.information
            ),
            confidence=0.80,
            severity=EvidenceSeverity.MEDIUM,
        )

    @classmethod
    def _build_generic_rejection(
        cls,
        row: RawTraceRow,
    ) -> ParsedEvidence:
        return cls._create_evidence(
            row=row,
            evidence_type=EvidenceType.REJECTION,
            category="reject_signal",
            value=cls._extract_error_value(
                row.information
            ),
            confidence=0.80,
            severity=EvidenceSeverity.MEDIUM,
        )

    @staticmethod
    def _create_evidence(
        *,
        row: RawTraceRow,
        evidence_type: EvidenceType,
        category: str,
        value: str,
        confidence: float,
        severity: EvidenceSeverity,
        protocol_layer: str | None = None,
        event_code: str | None = None,
        metric_name: str | None = None,
    ) -> ParsedEvidence:
        return ParsedEvidence.create(
            evidence_type=evidence_type,
            category=category,
            value=value,
            confidence=confidence,
            source_line_number=row.line_number,
            source_line=row.source_line,
            severity=severity,
            timestamp=row.timestamp,
            protocol_layer=protocol_layer,
            event_code=event_code,
            metric_name=metric_name,
            metadata={
                "event": row.event,
                "event_type": row.event_type,
                "call_id": row.call_id,
                "ptc": row.ptc,
            },
        )

    @staticmethod
    def _extract_error_value(
        information: str | None,
    ) -> str:
        if information is None:
            return "Unknown operational error"

        normalized_information = information.strip()

        if not normalized_information:
            return "Unknown operational error"

        error_match = EvidenceExtractor._split_case_insensitive(
            normalized_information,
            "error",
        )

        if error_match is not None:
            extracted = error_match.strip(
                " ;:=,\"'"
            )

            if extracted:
                return extracted

        if "=" in normalized_information:
            extracted = normalized_information.split(
                "=",
                maxsplit=1,
            )[1].strip(
                " ;,\"'"
            )

            if extracted:
                return extracted

        return normalized_information

    @staticmethod
    def _split_case_insensitive(
        value: str,
        separator: str,
    ) -> str | None:
        lowered_value = value.casefold()
        lowered_separator = separator.casefold()

        position = lowered_value.find(
            lowered_separator
        )

        if position < 0:
            return None

        return value[
            position + len(separator):
        ]

    @staticmethod
    def _normalize_for_matching(
        information: str,
    ) -> str:
        """
        Produce a stable representation for deterministic keyword rules.

        Whitespace is collapsed so variants such as repeated spaces,
        tabs, and line breaks do not require separate rules.
        """

        return " ".join(
            information.casefold().split()
        )
