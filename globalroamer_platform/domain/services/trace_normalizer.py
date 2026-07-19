#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from globalroamer_ai.models.operational_models import OperationalEvent, ParsedEvidence, ParsedTrace

logger = logging.getLogger("trace_normalizer")


class TraceNormalizer:
    def normalize(self, parsed: ParsedTrace) -> list[OperationalEvent]:
        events = []

        for index, evidence in enumerate(parsed.evidences, start=1):
            event = self._evidence_to_event(parsed, evidence, index)

            if event:
                events.append(event)

        logger.info(f"Normalized {len(events)} operational events for testcase {parsed.source.testcase_id}")
        return events

    def _evidence_to_event(self, parsed: ParsedTrace, evidence: ParsedEvidence, index: int) -> OperationalEvent:
        event_name = self._event_name(evidence)
        event_family = self._event_family(evidence)
        severity = self._severity(evidence)
        cause = self._cause(evidence)
        tags = self._tags(evidence)

        return OperationalEvent(
            testcase_id=parsed.source.testcase_id,
            event_id=f"{parsed.source.testcase_id}-{index:04d}",
            timestamp=evidence.timestamp,
            event_family=event_family,
            protocol_layer=evidence.protocol_layer or "unknown",
            event_name=event_name,
            severity=severity,
            raw_message=evidence.source_line,
            normalized_message=self._normalized_message(parsed, evidence, event_name, cause),
            direction=self._direction(evidence),
            workflow_stage=self._workflow_stage(evidence),
            network_domain=self._network_domain(evidence),
            operator=parsed.extracted_values.get("operator"),
            country=parsed.extracted_values.get("country"),
            result=self._result(evidence),
            cause=cause,
            source_trace=parsed.source.trace_path,
            extracted_values=parsed.extracted_values,
            tags=tags,
            evidences=[evidence.source_line],
            metadata={
                "evidence_type": evidence.evidence_type,
                "evidence_category": evidence.category,
                "evidence_value": evidence.value,
                "confidence": evidence.confidence,
                "metric_name": evidence.metric_name,
                "event_code": evidence.event_code,
                "source_event": evidence.metadata.get("event"),
                "source_type": evidence.metadata.get("type"),
                "recommendation": self._recommendation(evidence),
                "retry_recommended": self._retry_recommended(evidence),
            },
        )

    @staticmethod
    def _event_name(evidence: ParsedEvidence) -> str:
        mapping = {
            "plmn_not_allowed": "PLMN_NOT_ALLOWED",
            "location_update_failed": "LOCATION_UPDATE_FAILED",
            "location_update_reject": "MM_LOCATION_UPDATE_REJECT",
            "location_update_request": "MM_LOCATION_UPDATE_REQUEST",
            "registration_denied": "REGISTRATION_DENIED",
            "nas_registered": "NAS_REGISTERED",
            "nas_not_registered": "NAS_NOT_REGISTERED",
            "ps_attached": "PS_ATTACHED",
            "detached": "DETACHED",
            "timeout": "TIMEOUT",
            "retry_detected": "RETRY_DETECTED",
            "failure_signal": "FAILURE_SIGNAL",
            "reject_signal": "REJECT_SIGNAL",
        }

        return mapping.get(evidence.category, evidence.category.upper())

    @staticmethod
    def _event_family(evidence: ParsedEvidence) -> str:
        if evidence.evidence_type == "mobility_management":
            return "mobility_management"

        if evidence.evidence_type == "network_state":
            return "network_state"

        if evidence.evidence_type == "retry":
            return "retry"

        if evidence.evidence_type == "timing":
            return "timing"

        if evidence.evidence_type in {"failure", "rejection"}:
            return "failure"

        return "generic"

    @staticmethod
    def _severity(evidence: ParsedEvidence) -> str:
        if evidence.category in {
            "plmn_not_allowed", "location_update_failed", "location_update_reject", "registration_denied"
        }:
            return "high"

        if evidence.category in {
            "timeout", "retry_detected", "nas_not_registered", "detached", "failure_signal", "reject_signal"
        }:
            return "medium"

        return evidence.severity or "info"

    @staticmethod
    def _cause(evidence: ParsedEvidence) -> str | None:
        mapping = {
            "plmn_not_allowed": "PLMN_NOT_ALLOWED",
            "location_update_failed": "LOCATION_UPDATE_FAILED",
            "location_update_reject": "LOCATION_UPDATE_REJECT",
            "registration_denied": "REGISTRATION_DENIED",
            "timeout": "TIMEOUT",
            "retry_detected": "RETRY",
            "nas_not_registered": "NAS_NOT_REGISTERED",
            "detached": "DETACHED",
        }

        return mapping.get(evidence.category)

    @staticmethod
    def _workflow_stage(evidence: ParsedEvidence) -> str:
        if evidence.category in {
            "location_update_request", "location_update_reject",
            "location_update_failed", "plmn_not_allowed", "registration_denied"
        }:
            return "mobility_management"

        if evidence.category in {"nas_registered", "nas_not_registered", "ps_attached", "detached"}:
            return "network_registration"

        if evidence.category in {"timeout", "retry_detected"}:
            return "stability_or_retry"

        return "trace_analysis"

    @staticmethod
    def _network_domain(evidence: ParsedEvidence) -> str:
        if evidence.evidence_type in {"mobility_management", "network_state"}:
            return "roaming"

        if evidence.category in {"timeout", "retry_detected"}:
            return "connectivity"

        return "unknown"

    @staticmethod
    def _direction(evidence: ParsedEvidence) -> str | None:
        text = evidence.source_line.lower()

        if "send" in text or "-->" in text:
            return "send"

        if "recv" in text or "<--" in text or "received" in text:
            return "receive"

        return None

    @staticmethod
    def _result(evidence: ParsedEvidence) -> str | None:
        if evidence.category in {
            "plmn_not_allowed", "location_update_failed", "location_update_reject",
            "registration_denied", "timeout", "failure_signal", "reject_signal"
        }:
            return "failed"

        if evidence.category in {"nas_registered", "ps_attached", "location_update_request"}:
            return "observed"

        return None

    @staticmethod
    def _tags(evidence: ParsedEvidence) -> list[str]:
        tags = [evidence.evidence_type, evidence.category]

        if evidence.protocol_layer:
            tags.append(evidence.protocol_layer.lower())

        if evidence.severity:
            tags.append(evidence.severity)

        return sorted(set(tags))

    @staticmethod
    def _recommendation(evidence: ParsedEvidence) -> str | None:
        if evidence.category == "plmn_not_allowed":
            return "Check HPLMN/VPLMN roaming agreement, SIM profile and PLMN authorization."

        if evidence.category in {"location_update_failed", "location_update_reject", "registration_denied"}:
            return "Review MM location update flow, reject cause, HPLMN/VPLMN configuration and operator restrictions."

        if evidence.category == "timeout":
            return "Check network stability, timeout thresholds, radio state and transport delays."

        if evidence.category == "retry_detected":
            return "Compare retry count with historical successful retries before escalation."

        if evidence.category in {"nas_not_registered", "detached"}:
            return "Check registration state, attach state and radio/network availability."

        return None

    @staticmethod
    def _retry_recommended(evidence: ParsedEvidence) -> bool:
        if evidence.category in {"plmn_not_allowed", "registration_denied", "location_update_reject"}:
            return False

        if evidence.category in {"timeout", "retry_detected", "nas_not_registered", "detached"}:
            return True

        return False

    @staticmethod
    def _normalized_message(parsed: ParsedTrace, evidence: ParsedEvidence, event_name: str, cause: str | None) -> str:
        operator = parsed.extracted_values.get("operator", "unknown_operator")
        country = parsed.extracted_values.get("country", "unknown_country")
        value = evidence.value or "unknown"

        if cause:
            return f"{event_name} detected for operator={operator}, country={country}, cause={cause}, value={value}"

        return f"{event_name} detected for operator={operator}, country={country}, value={value}"
