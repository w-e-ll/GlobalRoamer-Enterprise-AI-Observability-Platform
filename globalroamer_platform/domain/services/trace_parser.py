#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import logging
import re
import yaml

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from globalroamer_ai.core.exceptions import TraceParserError
from globalroamer_ai.models.operational_models import ParsedEvidence, ParsedTrace, SourceArtifact

logger = logging.getLogger("trace_parser")


class TraceParser:
    def parse(self, source: SourceArtifact, mapping_path: str | None = None) -> ParsedTrace:
        if not source.trace_path:
            raise TraceParserError(f"Missing trace path for testcase {source.testcase_id}")

        rows = self._read_csv_rows(source.trace_path)
        lines = [row.get("Information", "") for row in rows if row.get("Information")]

        extracted_values = self._extract_base_values(rows)
        parser_errors = []

        if mapping_path:
            try:
                mapping = yaml.safe_load(Path(mapping_path).read_text(encoding="utf-8")) or []
                extracted_values.update(self._parse_with_mapping(lines, mapping, source, parser_errors))
            except Exception as exc:
                parser_errors.append(f"mapping_parse_failed:{mapping_path}:{exc}")

        evidences = self._extract_evidences(rows)
        raw_signals = [evidence.source_line for evidence in evidences]

        return ParsedTrace(
            source=source,
            extracted_values=extracted_values,
            evidences=evidences,
            raw_signals=raw_signals,
            parser_errors=parser_errors
        )

    def _read_csv_rows(self, trace_path: str) -> list[dict[str, str]]:
        path = Path(trace_path)

        if not path.exists():
            raise TraceParserError(f"Trace file not found: {trace_path}")

        try:
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                rows = [dict(row) for row in reader]

            logger.info(f"Read {len(rows)} trace rows from {path.name}")
            return rows

        except Exception as exc:
            raise TraceParserError(f"Failed to read trace CSV {trace_path}: {exc}")

    def _extract_base_values(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        values = {}

        interesting_keys = {
            "PTC_A.Country": "country",
            "PTC_A.Location": "location",
            "PTC_A.Plmn": "operator",
            "PTC_A.Imsi": "imsi",
            "PTC_A.Msisdn": "msisdn",
            "PTC_A.ResourceType": "resource_type",
            "PTC_A.ResourceModes": "resource_modes",
            "PTC_A.ResourceOptions": "resource_options",
            "PtcStartTimestamp": "ptc_start_timestamp",
            "TestExecutionStartTime": "test_execution_start_time",
        }

        for row in rows:
            information = row.get("Information", "") or ""

            for raw_key, normalized_key in interesting_keys.items():
                if raw_key in information and normalized_key not in values:
                    extracted = self._extract_assignment_value(information)
                    if extracted is not None:
                        values[normalized_key] = extracted

        return values

    def _extract_evidences(self, rows: list[dict[str, str]]) -> list[ParsedEvidence]:
        evidences = []

        for row in rows:
            information = row.get("Information", "") or ""
            event = row.get("Event", "") or ""
            event_type = row.get("Type", "") or ""
            timestamp = self._parse_timestamp(row.get("Timestamp"))
            source_line = self._build_source_line(row)
            lowered = information.lower()

            evidence = self._classify_evidence(information, lowered, event, event_type, timestamp, source_line)

            if evidence:
                evidences.append(evidence)

        logger.info(f"Extracted {len(evidences)} evidences")
        return evidences

    def _classify_evidence(
            self,
            information: str,
            lowered: str,
            event: str,
            event_type: str,
            timestamp: datetime | None,
            source_line: str
    ) -> ParsedEvidence | None:
        if "plmn not allowed" in lowered:
            return ParsedEvidence(
                evidence_type="mobility_management",
                category="plmn_not_allowed",
                value="PLMN not allowed",
                confidence=0.98,
                source_line=source_line,
                protocol_layer="MM",
                event_code="11",
                metric_name=None,
                severity="high",
                timestamp=timestamp,
                metadata={"event": event, "type": event_type}
            )

        if "locationupdate failed" in lowered or "location update failed" in lowered:
            return ParsedEvidence(
                evidence_type="mobility_management",
                category="location_update_failed",
                value=self._extract_error_value(information),
                confidence=0.95, source_line=source_line,
                protocol_layer="MM",
                event_code=None,
                metric_name=None,
                severity="high",
                timestamp=timestamp,
                metadata={"event": event, "type": event_type}
            )

        if "mm location updating reject" in lowered:
            return ParsedEvidence(
                evidence_type="mobility_management",
                category="location_update_reject",
                value="MM Location updating reject",
                confidence=0.95,
                source_line=source_line,
                protocol_layer="MM",
                event_code=None,
                metric_name=None,
                severity="high",
                timestamp=timestamp,
                metadata={"event": event, "type": event_type}
            )

        if "mm location updating request" in lowered:
            return ParsedEvidence(
                evidence_type="mobility_management",
                category="location_update_request",
                value="MM Location updating request",
                confidence=0.90,
                source_line=source_line,
                protocol_layer="MM",
                event_code=None,
                metric_name=None,
                severity="info",
                timestamp=timestamp,
                metadata={"event": event, "type": event_type}
            )

        if "registration denied" in lowered:
            return ParsedEvidence(
                evidence_type="mobility_management",
                category="registration_denied",
                value="registration denied",
                confidence=0.95,
                source_line=source_line,
                protocol_layer="MM",
                event_code=None,
                metric_name=None,
                severity="high",
                timestamp=timestamp,
                metadata={"event": event, "type": event_type}
            )

        if "nasregistered" in lowered or "registrationstate nasregistered" in lowered:
            return ParsedEvidence(
                evidence_type="network_state",
                category="nas_registered",
                value="NASRegistered",
                confidence=0.85,
                source_line=source_line,
                protocol_layer="NAS",
                event_code=None,
                metric_name=None,
                severity="info",
                timestamp=timestamp,
                metadata={"event": event, "type": event_type}
            )

        if "nasnotregistered" in lowered or "registrationstate nasnotregistered" in lowered:
            return ParsedEvidence(
                evidence_type="network_state",
                category="nas_not_registered",
                value="NASNotRegistered",
                confidence=0.90,
                source_line=source_line,
                protocol_layer="NAS",
                event_code=None,
                metric_name=None,
                severity="medium",
                timestamp=timestamp,
                metadata={"event": event, "type": event_type}
            )

        if "psattachstate attached" in lowered or "psattached" in lowered:
            return ParsedEvidence(
                evidence_type="network_state",
                category="ps_attached",
                value="PSAttached",
                confidence=0.85,
                source_line=source_line,
                protocol_layer="NAS",
                event_code=None,
                metric_name=None,
                severity="info",
                timestamp=timestamp,
                metadata={"event": event, "type": event_type}
            )

        if "psattachstate detached" in lowered or "detached" in lowered:
            return ParsedEvidence(
                evidence_type="network_state",
                category="detached",
                value="Detached",
                confidence=0.80,
                source_line=source_line,
                protocol_layer="NAS",
                event_code=None,
                metric_name=None,
                severity="medium",
                timestamp=timestamp,
                metadata={"event": event, "type": event_type}
            )

        if "timeout" in lowered:
            return ParsedEvidence(
                evidence_type="timing",
                category="timeout",
                value="timeout",
                confidence=0.85,
                source_line=source_line,
                protocol_layer=None,
                event_code=None,
                metric_name="timeout",
                severity="medium",
                timestamp=timestamp,
                metadata={"event": event, "type": event_type}
            )

        if "retry" in lowered or "retransmission" in lowered:
            return ParsedEvidence(
                evidence_type="retry",
                category="retry_detected",
                value="retry",
                confidence=0.80,
                source_line=source_line,
                protocol_layer=None,
                event_code=None,
                metric_name="retry_count",
                severity="medium",
                timestamp=timestamp,
                metadata={"event": event, "type": event_type}
            )

        if "fail" in lowered or "failed" in lowered or "failure" in lowered:
            return ParsedEvidence(
                evidence_type="failure",
                category="failure_signal",
                value=self._extract_error_value(information),
                confidence=0.80,
                source_line=source_line,
                protocol_layer=None,
                event_code=None,
                metric_name=None,
                severity="medium",
                timestamp=timestamp,
                metadata={"event": event, "type": event_type}
            )

        if "reject" in lowered or "rejected" in lowered:
            return ParsedEvidence(
                evidence_type="rejection",
                category="reject_signal",
                value=self._extract_error_value(information),
                confidence=0.80,
                source_line=source_line,
                protocol_layer=None,
                event_code=None,
                metric_name=None,
                severity="medium",
                timestamp=timestamp,
                metadata={"event": event, "type": event_type}
            )

        return None

    def _parse_with_mapping(
            self,
            lines: list[str],
            mapping: list[dict[str, Any]],
            source: SourceArtifact,
            errors: list[str]
    ) -> dict[str, Any]:
        result = {}
        time_adjustment = self._parse_time_change(source.time_change)

        for variable in mapping:
            value = variable.get("value")

            if not value:
                continue

            try:
                if value.startswith("time("):
                    self._extract_time_value(lines, value, result, time_adjustment)
                else:
                    self._extract_regex_value(lines, value, result)
            except Exception as exc:
                errors.append(f"mapping_failed:{value}:{exc}")

        return result

    def _extract_regex_value(self, lines: list[str], value: str, result: dict[str, Any]) -> None:
        if ";" in value:
            pattern = re.compile(value)
        else:
            pattern = re.compile(value.replace(".", r"\.") + r";\s*(.+)")

        for line in lines:
            match = pattern.search(line)

            if not match:
                continue

            if "=" in line:
                result[value] = line.split("=")[1].split(";")[0].replace(",", "").strip().strip("'").strip('"')
            else:
                result[value] = match.group(0).strip()

            return

    def _extract_time_value(
            self,
            lines: list[str],
            expression: str,
            result: dict[str, Any],
            time_adjustment: timedelta
    ) -> None:
        param = expression.split(",")[0].replace("time(", "").strip()
        param_filter = expression.split(",")[1].replace(")", "").strip()
        pattern = re.compile(param.replace(".", r"\.") + r"[:;]\s*(.+)")

        for line in lines:
            match = pattern.search(line)

            if not match:
                continue

            raw = match.group(1)
            timestamp_ms = self._extract_timestamp_ms(raw)

            if timestamp_ms is None:
                continue

            dt = datetime.fromtimestamp(timestamp_ms / 1000) + time_adjustment
            result.setdefault(param, {})
            result[param]["unix"] = dt.isoformat()
            result[param][param_filter] = self._format_time(dt, param_filter)
            return

    @staticmethod
    def _extract_assignment_value(information: str) -> str | None:
        if "=" not in information:
            return None

        value = information.split("=", 1)[1].strip()
        value = value.split(";", 1)[0].strip()
        return value.strip("'").strip('"')

    @staticmethod
    def _extract_error_value(information: str) -> str:
        if "Error" in information:
            return information.split("Error", 1)[-1].strip(" ;:=,\"'")

        if "=" in information:
            return information.split("=", 1)[-1].strip(" ;,\"'")

        return information.strip()

    @staticmethod
    def _extract_timestamp_ms(raw: str) -> int | None:
        patterns = [
            r"DATETIME\((\d{10,16})\)",
            r"DATETIME\s*=\s*(\d{10,16})",
            r"(\d{13,16})",
        ]

        for pattern in patterns:
            match = re.search(pattern, raw)

            if match:
                return int(match.group(1))

        return None

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if not value or value == "<null>":
            return None

        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S.%f")
        except Exception:
            return None

    @staticmethod
    def _build_source_line(row: dict[str, str]) -> str:
        return ";".join([
            row.get("Timestamp", "") or "",
            row.get("CallId", "") or "",
            row.get("Ptc", "") or "",
            row.get("Event", "") or "",
            row.get("Type", "") or "",
            row.get("Information", "") or "",
        ])

    @staticmethod
    def _format_time(dt: datetime, param_filter: str) -> str:
        values = {
            "hour": dt.strftime("%H"),
            "min": dt.strftime("%M"),
            "sec": dt.strftime("%S"),
            "date": dt.strftime("%Y-%m-%d"),
            "h:m:s": dt.strftime("%H:%M:%S"),
        }

        return values.get(param_filter, dt.isoformat())

    @staticmethod
    def _parse_time_change(value: str) -> timedelta:
        value = value or "0"
        sign = -1 if value.startswith("-") else 1
        parts = value.lstrip("+-").split(":")
        hours = int(parts[0]) if parts and parts[0].isdigit() else 0
        minutes = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return timedelta(hours=hours * sign, minutes=minutes * sign)


def parse_trace_content(content: str, metadata: dict | None = None) -> dict:
    metadata = metadata or {}
    lines = content.splitlines()
    events = []

    for line_number, line in enumerate(lines, start=1):
        line = line.strip()

        if not line:
            continue

        events.append({
            "line_number": line_number,
            "raw": line,
            "event_name": line.split(";")[4] if len(line.split(";")) > 4 else "unknown",
            "timestamp": None,
            "fields": {},
            "signals": extract_operational_signals(line),
        })

    return {
        "trace_id": metadata.get("filename"),
        "metadata": metadata,
        "event_count": len(events),
        "events": events,
    }


def extract_operational_signals(line: str) -> list[str]:
    lowered = line.lower()
    signals = []

    patterns = {
        "failure": ["fail", "failed", "failure"],
        "error": ["error", "exception"],
        "timeout": ["timeout", "timed out"],
        "retry": ["retry", "retransmission"],
        "detach": ["detach", "detached"],
        "attach": ["attach", "attached"],
        "registration": ["registration", "register"],
        "authentication": ["auth", "authentication"],
        "paging": ["paging"],
        "reject": ["reject", "rejected"],
        "disconnect": ["disconnect", "disconnected"],
        "release": ["release", "released"],
        "sms": ["sms"],
        "call": ["call", "voice"],
        "volte": ["volte", "ims"],
    }

    for signal, keywords in patterns.items():
        if any(keyword in lowered for keyword in keywords):
            signals.append(signal)

    return signals
