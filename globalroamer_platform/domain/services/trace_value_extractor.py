from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from globalroamer_platform.domain.models.extracted_trace_values import (
    ExtractedTraceValues,
    ExtractedValue,
)
from globalroamer_platform.domain.models.raw_trace import (
    RawTrace,
    RawTraceRow,
)


@dataclass(frozen=True, slots=True)
class AssignmentMatch:
    """Represent one key-value assignment found in a trace row."""

    name: str
    value: str
    expression: str


class TraceValueExtractor:
    """
    Extract unprocessed values from structurally parsed trace rows.

    The extractor supports common assignment representations such as:

        IMSI=206012345678901
        MCC: 206
        registrationState = NASRegistered
        timeout 30000
        lac="1234"

    It does not:

    - load YAML mappings;
    - translate vendor-specific values;
    - normalize timestamps into a common timezone;
    - classify evidence;
    - detect operational signals;
    - make telecom-domain decisions.

    When the same field occurs multiple times, the configured duplicate
    strategy determines which value is retained.
    """

    _FIELD_NAME_PATTERN: Final[str] = (
        r"[A-Za-z_][A-Za-z0-9_.\-/]*"
    )

    _QUOTED_ASSIGNMENT_PATTERN: Final[re.Pattern[str]] = re.compile(
        rf"""
        (?P<name>{_FIELD_NAME_PATTERN})
        \s*
        (?P<separator>=|:)
        \s*
        (?P<quote>["'])
        (?P<value>.*?)
        (?P=quote)
        """,
        re.VERBOSE,
    )

    _UNQUOTED_ASSIGNMENT_PATTERN: Final[re.Pattern[str]] = re.compile(
        rf"""
        (?P<name>{_FIELD_NAME_PATTERN})
        \s*
        (?P<separator>=|:)
        \s*
        (?P<value>
            [^;,\r\n]+?
        )
        (?=
            \s+[A-Za-z_][A-Za-z0-9_.\-/]*\s*(?:=|:)
            |
            [;,\r\n]
            |
            $
        )
        """,
        re.VERBOSE,
    )

    _WHITESPACE_ASSIGNMENT_PATTERN: Final[re.Pattern[str]] = re.compile(
        rf"""
        ^
        \s*
        (?P<name>{_FIELD_NAME_PATTERN})
        \s+
        (?P<value>\S(?:.*?\S)?)
        \s*
        $
        """,
        re.VERBOSE,
    )

    _VALID_DUPLICATE_STRATEGIES: Final[frozenset[str]] = frozenset(
        {
            "first",
            "last",
            "warn_first",
            "warn_last",
        }
    )

    def __init__(
        self,
        *,
        duplicate_strategy: str = "warn_last",
        include_event: bool = True,
        include_event_type: bool = True,
        include_raw_fields: bool = True,
        allow_whitespace_assignments: bool = False,
    ) -> None:
        normalized_strategy = duplicate_strategy.strip().casefold()

        if normalized_strategy not in self._VALID_DUPLICATE_STRATEGIES:
            supported = ", ".join(
                sorted(self._VALID_DUPLICATE_STRATEGIES)
            )
            raise ValueError(
                "Unsupported duplicate strategy "
                f"'{duplicate_strategy}'. Supported values: {supported}"
            )

        self._duplicate_strategy = normalized_strategy
        self._include_event = include_event
        self._include_event_type = include_event_type
        self._include_raw_fields = include_raw_fields
        self._allow_whitespace_assignments = (
            allow_whitespace_assignments
        )

    @property
    def duplicate_strategy(self) -> str:
        return self._duplicate_strategy

    def extract(
        self,
        trace: RawTrace,
    ) -> ExtractedTraceValues:
        """Extract values from all rows of a raw trace."""

        extracted_values: dict[str, ExtractedValue] = {}
        warnings: list[str] = []

        for row in trace.rows:
            self._extract_row_values(
                row=row,
                destination=extracted_values,
                warnings=warnings,
            )

        return ExtractedTraceValues.create(
            values=extracted_values,
            extraction_warnings=tuple(warnings),
        )

    def extract_from_row(
        self,
        row: RawTraceRow,
    ) -> ExtractedTraceValues:
        """Extract values from a single raw trace row."""

        extracted_values: dict[str, ExtractedValue] = {}
        warnings: list[str] = []

        self._extract_row_values(
            row=row,
            destination=extracted_values,
            warnings=warnings,
        )

        return ExtractedTraceValues.create(
            values=extracted_values,
            extraction_warnings=tuple(warnings),
        )

    def _extract_row_values(
        self,
        *,
        row: RawTraceRow,
        destination: dict[str, ExtractedValue],
        warnings: list[str],
    ) -> None:
        sources = self._build_extraction_sources(row)

        for source_name, content in sources:
            if not content or not content.strip():
                continue

            assignments = self._find_assignments(content)

            for assignment in assignments:
                extracted_value = ExtractedValue(
                    name=self._normalize_field_name(
                        assignment.name
                    ),
                    value=self._coerce_value(
                        assignment.value
                    ),
                    source_line_number=row.line_number,
                    source_expression=assignment.expression,
                    extraction_method="assignment",
                    confidence=1.0,
                    metadata={
                        "source_column": source_name,
                        "event": row.event,
                        "event_type": row.event_type,
                        "call_id": row.call_id,
                        "ptc": row.ptc,
                    },
                )

                self._store_value(
                    destination=destination,
                    extracted_value=extracted_value,
                    warnings=warnings,
                )

    def _build_extraction_sources(
        self,
        row: RawTraceRow,
    ) -> tuple[tuple[str, str | None], ...]:
        sources: list[tuple[str, str | None]] = [
            (
                "information",
                row.information,
            )
        ]

        if self._include_event:
            sources.append(
                (
                    "event",
                    row.event,
                )
            )

        if self._include_event_type:
            sources.append(
                (
                    "event_type",
                    row.event_type,
                )
            )

        if self._include_raw_fields:
            for field_name, field_value in row.raw_fields.items():
                if field_name.casefold() in {
                    "information",
                    "event",
                    "type",
                    "event_type",
                }:
                    continue

                if field_value is None:
                    continue

                sources.append(
                    (
                        f"raw_fields.{field_name}",
                        str(field_value),
                    )
                )

        return tuple(sources)

    def _find_assignments(
        self,
        content: str,
    ) -> tuple[AssignmentMatch, ...]:
        matches: list[AssignmentMatch] = []
        occupied_ranges: list[tuple[int, int]] = []

        for match in self._QUOTED_ASSIGNMENT_PATTERN.finditer(
            content
        ):
            assignment = self._create_assignment_match(match)

            if assignment is not None:
                matches.append(assignment)
                occupied_ranges.append(
                    match.span()
                )

        for match in self._UNQUOTED_ASSIGNMENT_PATTERN.finditer(
            content
        ):
            if self._overlaps_existing_match(
                match.span(),
                occupied_ranges,
            ):
                continue

            assignment = self._create_assignment_match(match)

            if assignment is not None:
                matches.append(assignment)
                occupied_ranges.append(
                    match.span()
                )

        if (
            not matches
            and self._allow_whitespace_assignments
        ):
            whitespace_match = (
                self._WHITESPACE_ASSIGNMENT_PATTERN.match(
                    content
                )
            )

            if whitespace_match is not None:
                assignment = self._create_assignment_match(
                    whitespace_match
                )

                if assignment is not None:
                    matches.append(assignment)

        return tuple(matches)

    @staticmethod
    def _create_assignment_match(
        match: re.Match[str],
    ) -> AssignmentMatch | None:
        name = match.group("name").strip()
        value = match.group("value").strip()
        expression = match.group(0).strip()

        if not name or not value:
            return None

        return AssignmentMatch(
            name=name,
            value=value,
            expression=expression,
        )

    @staticmethod
    def _overlaps_existing_match(
        candidate: tuple[int, int],
        existing_ranges: list[tuple[int, int]],
    ) -> bool:
        candidate_start, candidate_end = candidate

        return any(
            candidate_start < existing_end
            and candidate_end > existing_start
            for existing_start, existing_end in existing_ranges
        )

    def _store_value(
        self,
        *,
        destination: dict[str, ExtractedValue],
        extracted_value: ExtractedValue,
        warnings: list[str],
    ) -> None:
        existing_value = destination.get(
            extracted_value.name
        )

        if existing_value is None:
            destination[extracted_value.name] = extracted_value
            return

        if existing_value.value == extracted_value.value:
            return

        warning = (
            f"Duplicate extracted value '{extracted_value.name}': "
            f"line {existing_value.source_line_number} contains "
            f"{existing_value.value!r}, while line "
            f"{extracted_value.source_line_number} contains "
            f"{extracted_value.value!r}"
        )

        if self._duplicate_strategy.startswith("warn_"):
            warnings.append(warning)

        if self._duplicate_strategy in {
            "last",
            "warn_last",
        }:
            destination[extracted_value.name] = extracted_value

    @staticmethod
    def _normalize_field_name(
        name: str,
    ) -> str:
        """
        Normalize a field name without changing its domain meaning.

        Case is preserved because mapping configuration may depend on
        vendor-specific capitalization.
        """

        return name.strip()

    @classmethod
    def _coerce_value(
        cls,
        value: str,
    ) -> Any:
        """
        Apply conservative primitive type conversion.

        Telecom identifiers with meaningful leading zeroes remain strings.
        More specialized conversion belongs to MappingEngine or a
        dedicated value normalizer.
        """

        normalized = cls._strip_wrapping_characters(
            value
        )

        casefolded_value = normalized.casefold()

        if casefolded_value == "true":
            return True

        if casefolded_value == "false":
            return False

        if casefolded_value in {
            "none",
            "null",
        }:
            return normalized

        if cls._is_safe_integer(normalized):
            try:
                return int(normalized)
            except ValueError:
                return normalized

        if cls._is_safe_float(normalized):
            try:
                return float(normalized)
            except ValueError:
                return normalized

        parsed_datetime = cls._try_parse_iso_datetime(
            normalized
        )

        if parsed_datetime is not None:
            return parsed_datetime

        return normalized

    @staticmethod
    def _strip_wrapping_characters(
        value: str,
    ) -> str:
        normalized = value.strip().rstrip(
            ";,"
        ).strip()

        if (
            len(normalized) >= 2
            and normalized[0] == normalized[-1]
            and normalized[0] in {
                '"',
                "'",
            }
        ):
            return normalized[1:-1].strip()

        return normalized

    @staticmethod
    def _is_safe_integer(
        value: str,
    ) -> bool:
        if not re.fullmatch(
            r"[+-]?\d+",
            value,
        ):
            return False

        unsigned_value = value.lstrip(
            "+-"
        )

        if len(unsigned_value) > 1 and unsigned_value.startswith("0"):
            return False

        # Long digit sequences are commonly IMSI, MSISDN, ICCID or
        # similar identifiers rather than quantities.
        return len(unsigned_value) <= 10

    @staticmethod
    def _is_safe_float(
        value: str,
    ) -> bool:
        return bool(
            re.fullmatch(
                r"[+-]?(?:\d+\.\d+|\d+\.\d*|\.\d+)",
                value,
            )
        )

    @staticmethod
    def _try_parse_iso_datetime(
        value: str,
    ) -> datetime | None:
        if "T" not in value and " " not in value:
            return None

        candidate = value

        if candidate.endswith("Z"):
            candidate = (
                candidate[:-1]
                + "+00:00"
            )

        try:
            return datetime.fromisoformat(
                candidate
            )
        except ValueError:
            return None
