from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from globalroamer_platform.domain.models.extracted_trace_values import (
    ExtractedTraceValues,
)
from globalroamer_platform.domain.models.mapped_trace_values import (
    MappedTraceValues,
)
from globalroamer_platform.domain.models.operational_signal import (
    OperationalSignal,
)
from globalroamer_platform.domain.models.parsed_evidence import (
    ParsedEvidence,
)
from globalroamer_platform.domain.models.raw_trace import RawTrace


@dataclass(frozen=True, slots=True)
class ParsedTrace:
    """
    Aggregate produced by the complete trace parsing pipeline.

    ParsedTrace assembles the outputs of independent parsing services
    without repeating their responsibilities:

        RawTrace
            ├── ExtractedTraceValues
            ├── MappedTraceValues
            ├── ParsedEvidence
            └── OperationalSignal

    The aggregate is immutable and suitable for passing from the domain
    pipeline into persistence, reporting, observability, or AI layers.
    """

    raw_trace: RawTrace
    extracted_values: ExtractedTraceValues
    mapped_values: MappedTraceValues

    evidences: tuple[ParsedEvidence, ...] = ()
    signals: tuple[OperationalSignal, ...] = ()

    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not isinstance(
            self.raw_trace,
            RawTrace,
        ):
            raise TypeError(
                "raw_trace must be a RawTrace"
            )

        if not isinstance(
            self.extracted_values,
            ExtractedTraceValues,
        ):
            raise TypeError(
                "extracted_values must be an ExtractedTraceValues"
            )

        if not isinstance(
            self.mapped_values,
            MappedTraceValues,
        ):
            raise TypeError(
                "mapped_values must be a MappedTraceValues"
            )

        normalized_evidences = tuple(
            self.evidences
        )
        normalized_signals = tuple(
            self.signals
        )

        for evidence in normalized_evidences:
            if not isinstance(
                evidence,
                ParsedEvidence,
            ):
                raise TypeError(
                    "evidences must contain ParsedEvidence objects"
                )

        for signal in normalized_signals:
            if not isinstance(
                signal,
                OperationalSignal,
            ):
                raise TypeError(
                    "signals must contain OperationalSignal objects"
                )

        object.__setattr__(
            self,
            "evidences",
            normalized_evidences,
        )
        object.__setattr__(
            self,
            "signals",
            normalized_signals,
        )
        object.__setattr__(
            self,
            "warnings",
            _normalize_messages(
                self.warnings
            ),
        )
        object.__setattr__(
            self,
            "errors",
            _normalize_messages(
                self.errors
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
        raw_trace: RawTrace,
        extracted_values: ExtractedTraceValues,
        mapped_values: MappedTraceValues,
        evidences: tuple[ParsedEvidence, ...] = (),
        signals: tuple[OperationalSignal, ...] = (),
        warnings: tuple[str, ...] = (),
        errors: tuple[str, ...] = (),
        metadata: Mapping[str, Any] | None = None,
        include_component_messages: bool = True,
    ) -> ParsedTrace:
        """
        Construct a parsed trace and optionally collect messages emitted
        by the component models.

        Explicit messages are retained first, followed by messages from:

        - RawTrace.parser_warnings;
        - ExtractedTraceValues.extraction_warnings;
        - MappedTraceValues.mapping_warnings;
        - MappedTraceValues.mapping_errors.
        """

        collected_warnings = list(
            warnings
        )
        collected_errors = list(
            errors
        )

        if include_component_messages:
            collected_warnings.extend(
                raw_trace.parser_warnings
            )
            collected_warnings.extend(
                extracted_values.extraction_warnings
            )
            collected_warnings.extend(
                mapped_values.mapping_warnings
            )
            collected_errors.extend(
                mapped_values.mapping_errors
            )

        return cls(
            raw_trace=raw_trace,
            extracted_values=extracted_values,
            mapped_values=mapped_values,
            evidences=evidences,
            signals=signals,
            warnings=_deduplicate_messages(
                collected_warnings
            ),
            errors=_deduplicate_messages(
                collected_errors
            ),
            metadata=metadata or {},
        )

    @property
    def source(self) -> str:
        return self.raw_trace.source

    @property
    def row_count(self) -> int:
        return len(
            self.raw_trace.rows
        )

    @property
    def evidence_count(self) -> int:
        return len(
            self.evidences
        )

    @property
    def signal_count(self) -> int:
        return len(
            self.signals
        )

    @property
    def extracted_value_count(self) -> int:
        return self.extracted_values.count

    @property
    def mapped_value_count(self) -> int:
        return self.mapped_values.count

    @property
    def has_warnings(self) -> bool:
        return bool(
            self.warnings
        )

    @property
    def has_errors(self) -> bool:
        return bool(
            self.errors
        )

    @property
    def is_valid(self) -> bool:
        """
        Indicate whether the pipeline completed without recorded errors.

        Warnings, missing optional mappings, or extracted evidence do not
        automatically make a parsed trace invalid.
        """

        return not self.has_errors

    @property
    def is_complete(self) -> bool:
        """
        Indicate whether mapping completed without missing or failed values.
        """

        return (
            self.is_valid
            and self.mapped_values.is_complete
        )

    @property
    def started_at(self) -> datetime | None:
        timestamps = self._timestamps

        if not timestamps:
            return None

        return min(
            timestamps
        )

    @property
    def ended_at(self) -> datetime | None:
        timestamps = self._timestamps

        if not timestamps:
            return None

        return max(
            timestamps
        )

    @property
    def duration_seconds(self) -> float | None:
        """
        Return trace duration when at least two compatible timestamps exist.

        Timestamps should normally already have been processed by
        TimeNormalizer before ParsedTrace is assembled.
        """

        started_at = self.started_at
        ended_at = self.ended_at

        if (
            started_at is None
            or ended_at is None
        ):
            return None

        try:
            return (
                ended_at - started_at
            ).total_seconds()
        except TypeError:
            # Mixed naive and timezone-aware values should not normally
            # reach this aggregate, but the model avoids hiding the rest
            # of a successfully parsed trace.
            return None

    @property
    def _timestamps(self) -> tuple[datetime, ...]:
        return tuple(
            row.timestamp
            for row in self.raw_trace.rows
            if isinstance(
                row.timestamp,
                datetime,
            )
        )

    def get_mapped_value(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        return self.mapped_values.get(
            name,
            default,
        )

    def get_extracted_value(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        return self.extracted_values.get(
            name,
            default,
        )

    def evidences_for_line(
        self,
        line_number: int,
    ) -> tuple[ParsedEvidence, ...]:
        if line_number <= 0:
            raise ValueError(
                "line_number must be greater than zero"
            )

        return tuple(
            evidence
            for evidence in self.evidences
            if evidence.source_line_number == line_number
        )

    def signals_for_line(
        self,
        line_number: int,
    ) -> tuple[OperationalSignal, ...]:
        if line_number <= 0:
            raise ValueError(
                "line_number must be greater than zero"
            )

        return tuple(
            signal
            for signal in self.signals
            if signal.source_line_number == line_number
        )

    def to_value_dict(
        self,
        *,
        include_defaults: bool = True,
    ) -> dict[str, Any]:
        """
        Return the flattened mapped values for downstream compatibility.
        """

        return self.mapped_values.to_value_dict(
            include_defaults=include_defaults
        )

    def to_dict(
        self,
        *,
        include_raw_rows: bool = True,
    ) -> dict[str, Any]:
        raw_trace_data = self._serialize_raw_trace(
            include_rows=include_raw_rows
        )

        return {
            "source": self.source,
            "raw_trace": raw_trace_data,
            "extracted_values": (
                self.extracted_values.to_dict()
            ),
            "mapped_values": (
                self.mapped_values.to_dict()
            ),
            "evidences": [
                evidence.to_dict()
                for evidence in self.evidences
            ],
            "signals": [
                signal.to_dict()
                for signal in self.signals
            ],
            "warnings": list(
                self.warnings
            ),
            "errors": list(
                self.errors
            ),
            "metadata": _serialize_value(
                dict(self.metadata)
            ),
            "summary": {
                "rows": self.row_count,
                "extracted_values": (
                    self.extracted_value_count
                ),
                "mapped_values": (
                    self.mapped_value_count
                ),
                "evidences": self.evidence_count,
                "signals": self.signal_count,
                "started_at": _serialize_value(
                    self.started_at
                ),
                "ended_at": _serialize_value(
                    self.ended_at
                ),
                "duration_seconds": (
                    self.duration_seconds
                ),
                "warnings": len(
                    self.warnings
                ),
                "errors": len(
                    self.errors
                ),
                "valid": self.is_valid,
                "complete": self.is_complete,
            },
        }

    def _serialize_raw_trace(
        self,
        *,
        include_rows: bool,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source": self.raw_trace.source,
            "delimiter": self.raw_trace.delimiter,
            "encoding": self.raw_trace.encoding,
            "parser_warnings": list(
                self.raw_trace.parser_warnings
            ),
            "row_count": self.row_count,
        }

        if include_rows:
            result["rows"] = [
                _serialize_raw_row(
                    row
                )
                for row in self.raw_trace.rows
            ]

        return result


def _serialize_raw_row(
    row: Any,
) -> dict[str, Any]:
    return {
        "line_number": row.line_number,
        "timestamp": _serialize_value(
            row.timestamp
        ),
        "call_id": row.call_id,
        "ptc": row.ptc,
        "event": row.event,
        "event_type": row.event_type,
        "information": row.information,
        "raw_fields": _serialize_value(
            dict(row.raw_fields)
        ),
        "source_line": row.source_line,
    }


def _normalize_messages(
    messages: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        message.strip()
        for message in messages
        if message and message.strip()
    )


def _deduplicate_messages(
    messages: list[str],
) -> tuple[str, ...]:
    """
    Deduplicate messages while preserving their original order.
    """

    result: list[str] = []
    seen: set[str] = set()

    for message in messages:
        normalized = message.strip()

        if not normalized or normalized in seen:
            continue

        seen.add(
            normalized
        )
        result.append(
            normalized
        )

    return tuple(
        result
    )


def _serialize_value(
    value: Any,
) -> Any:
    if isinstance(
        value,
        datetime,
    ):
        return value.isoformat()

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(key): _serialize_value(
                item
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        tuple,
    ):
        return [
            _serialize_value(
                item
            )
            for item in value
        ]

    if isinstance(
        value,
        list,
    ):
        return [
            _serialize_value(
                item
            )
            for item in value
        ]

    return value
