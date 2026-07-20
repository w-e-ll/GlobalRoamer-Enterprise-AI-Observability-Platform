# globalroamer_platform/domain/models/raw_trace.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from globalroamer_platform.domain.models.source_artifact import (
    SourceArtifact,
)


@dataclass(frozen=True, slots=True)
class RawTraceRow:
    """
    Represent one unclassified row from a source trace.

    This model preserves data extracted from the source file without
    applying telecom-specific interpretation or normalization.
    """

    line_number: int
    timestamp: datetime | None

    call_id: str | None
    ptc: str | None
    event: str | None
    event_type: str | None
    information: str | None

    raw_fields: Mapping[str, str | None]

    def __post_init__(self) -> None:
        if self.line_number <= 0:
            raise ValueError(
                "Raw trace row line_number must be greater than zero"
            )

        object.__setattr__(
            self,
            "call_id",
            _normalize_optional_text(self.call_id),
        )
        object.__setattr__(
            self,
            "ptc",
            _normalize_optional_text(self.ptc),
        )
        object.__setattr__(
            self,
            "event",
            _normalize_optional_text(self.event),
        )
        object.__setattr__(
            self,
            "event_type",
            _normalize_optional_text(self.event_type),
        )
        object.__setattr__(
            self,
            "information",
            _normalize_optional_text(self.information),
        )
        object.__setattr__(
            self,
            "raw_fields",
            MappingProxyType(
                {
                    str(key): _normalize_optional_text(value)
                    for key, value in self.raw_fields.items()
                }
            ),
        )

    @property
    def source_line(self) -> str:
        """
        Return a stable semicolon-separated representation of the row.

        This is useful for evidence references, debugging and later AI
        chunk construction.
        """

        values = (
            self._raw_value("Timestamp"),
            self.call_id,
            self.ptc,
            self.event,
            self.event_type,
            self.information,
        )

        return ";".join(
            value or ""
            for value in values
        )

    @property
    def has_information(self) -> bool:
        """Return whether the row contains a meaningful information field."""

        return self.information is not None

    def get(
        self,
        field_name: str,
        default: str | None = None,
    ) -> str | None:
        """Return an original source field by column name."""

        return self.raw_fields.get(
            field_name,
            default,
        )

    def _raw_value(
        self,
        field_name: str,
    ) -> str | None:
        return self.raw_fields.get(field_name)


@dataclass(frozen=True, slots=True)
class RawTrace:
    """
    Represent a trace after structural parsing but before interpretation.

    RawTrace is the output of TraceParser and the input for subsequent
    extraction and normalization services.
    """

    source: SourceArtifact
    rows: tuple[RawTraceRow, ...]

    delimiter: str
    encoding: str

    parser_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.delimiter:
            raise ValueError(
                "Raw trace delimiter must not be empty"
            )

        if len(self.delimiter) != 1:
            raise ValueError(
                "Raw trace delimiter must contain exactly one character"
            )

        normalized_encoding = self.encoding.strip()

        if not normalized_encoding:
            raise ValueError(
                "Raw trace encoding must not be empty"
            )

        object.__setattr__(
            self,
            "rows",
            tuple(self.rows),
        )
        object.__setattr__(
            self,
            "encoding",
            normalized_encoding,
        )
        object.__setattr__(
            self,
            "parser_warnings",
            tuple(
                warning.strip()
                for warning in self.parser_warnings
                if warning.strip()
            ),
        )

    @classmethod
    def create(
        cls,
        *,
        source: SourceArtifact,
        rows: list[RawTraceRow],
        delimiter: str,
        encoding: str,
        parser_warnings: list[str] | None = None,
    ) -> RawTrace:
        """Create an immutable raw trace from parser output."""

        return cls(
            source=source,
            rows=tuple(rows),
            delimiter=delimiter,
            encoding=encoding,
            parser_warnings=tuple(
                parser_warnings or ()
            ),
        )

    @property
    def row_count(self) -> int:
        """Return the number of parsed trace rows."""

        return len(self.rows)

    @property
    def is_empty(self) -> bool:
        """Return whether the trace contains no data rows."""

        return not self.rows

    @property
    def information_lines(self) -> tuple[str, ...]:
        """Return all non-empty Information values."""

        return tuple(
            row.information
            for row in self.rows
            if row.information is not None
        )

    @property
    def timestamps(self) -> tuple[datetime, ...]:
        """Return all successfully parsed timestamps."""

        return tuple(
            row.timestamp
            for row in self.rows
            if row.timestamp is not None
        )

    @property
    def earliest_timestamp(self) -> datetime | None:
        """Return the earliest parsed timestamp."""

        timestamps = self.timestamps

        return min(timestamps) if timestamps else None

    @property
    def latest_timestamp(self) -> datetime | None:
        """Return the latest parsed timestamp."""

        timestamps = self.timestamps

        return max(timestamps) if timestamps else None

    @property
    def duration_seconds(self) -> float | None:
        """Return trace duration based on parsed timestamps."""

        earliest = self.earliest_timestamp
        latest = self.latest_timestamp

        if earliest is None or latest is None:
            return None

        return (
            latest - earliest
        ).total_seconds()

    def row_at(
        self,
        line_number: int,
    ) -> RawTraceRow | None:
        """Return a row by its original source line number."""

        for row in self.rows:
            if row.line_number == line_number:
                return row

        return None

    def metadata(self) -> Mapping[str, Any]:
        """Return basic immutable trace metadata."""

        return MappingProxyType(
            {
                "artifact_id": str(self.source.id),
                "filename": self.source.filename,
                "row_count": self.row_count,
                "delimiter": self.delimiter,
                "encoding": self.encoding,
                "earliest_timestamp": (
                    self.earliest_timestamp.isoformat()
                    if self.earliest_timestamp
                    else None
                ),
                "latest_timestamp": (
                    self.latest_timestamp.isoformat()
                    if self.latest_timestamp
                    else None
                ),
                "duration_seconds": self.duration_seconds,
                "warning_count": len(
                    self.parser_warnings
                ),
            }
        )


def _normalize_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized_value = value.strip()

    return normalized_value or None
