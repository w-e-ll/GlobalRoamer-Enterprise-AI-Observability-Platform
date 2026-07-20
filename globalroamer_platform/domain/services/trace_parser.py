from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Final, TextIO

from globalroamer_platform.core.exceptions import TraceParserError
from globalroamer_platform.domain.models.raw_trace import (
    RawTrace,
    RawTraceRow,
)
from globalroamer_platform.domain.models.source_artifact import (
    SourceArtifact,
    SourceArtifactType,
)


DEFAULT_DELIMITER: Final[str] = ";"
DEFAULT_ENCODING: Final[str] = "utf-8"

EXPECTED_COLUMNS: Final[tuple[str, ...]] = (
    "Timestamp",
    "CallId",
    "Ptc",
    "Event",
    "Type",
    "Information",
)

TIMESTAMP_FORMATS: Final[tuple[str, ...]] = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
)


class TraceParser:
    """
    Parse a trace source into immutable raw trace rows.

    This service performs structural parsing only. It does not classify
    evidence, extract operational signals, apply mappings, normalize
    telecom values, or create AI chunks.
    """

    def __init__(
        self,
        *,
        delimiter: str = DEFAULT_DELIMITER,
        encoding: str = DEFAULT_ENCODING,
    ) -> None:
        if len(delimiter) != 1:
            raise ValueError(
                "Trace delimiter must contain exactly one character"
            )

        normalized_encoding = encoding.strip()

        if not normalized_encoding:
            raise ValueError(
                "Trace encoding must not be empty"
            )

        self._delimiter = delimiter
        self._encoding = normalized_encoding

    @property
    def delimiter(self) -> str:
        """Return the configured CSV delimiter."""

        return self._delimiter

    @property
    def encoding(self) -> str:
        """Return the configured source encoding."""

        return self._encoding

    def parse(
        self,
        source: SourceArtifact,
    ) -> RawTrace:
        """
        Parse one source artifact into a RawTrace.

        Invalid individual timestamps are retained as warnings rather
        than causing the entire trace to fail.
        """

        self._validate_source(source)

        warnings: list[str] = []

        try:
            with source.source_path.open(
                mode="r",
                encoding=self._encoding,
                errors="replace",
                newline="",
            ) as source_file:
                rows = self._parse_rows(
                    source_file,
                    warnings,
                )

        except TraceParserError:
            raise

        except (OSError, UnicodeError, csv.Error) as exc:
            raise TraceParserError(
                "Failed to parse trace file "
                f"{source.source_path}: {exc}"
            ) from exc

        if not rows:
            warnings.append(
                "Trace file contains no data rows"
            )

        return RawTrace.create(
            source=source,
            rows=rows,
            delimiter=self._delimiter,
            encoding=self._encoding,
            parser_warnings=warnings,
        )

    def _parse_rows(
        self,
        source_file: TextIO,
        warnings: list[str],
    ) -> list[RawTraceRow]:
        reader = csv.DictReader(
            source_file,
            delimiter=self._delimiter,
        )

        self._validate_header(
            reader.fieldnames
        )

        rows: list[RawTraceRow] = []

        # Header occupies physical source line 1.
        for line_number, raw_row in enumerate(
            reader,
            start=2,
        ):
            normalized_row = self._normalize_row(
                raw_row
            )

            timestamp_raw = normalized_row.get(
                "Timestamp"
            )
            timestamp = self._parse_timestamp(
                timestamp_raw
            )

            if (
                timestamp_raw is not None
                and timestamp is None
                and timestamp_raw != "<null>"
            ):
                warnings.append(
                    "Unrecognized timestamp at "
                    f"line {line_number}: {timestamp_raw}"
                )

            rows.append(
                RawTraceRow(
                    line_number=line_number,
                    timestamp=timestamp,
                    call_id=normalized_row.get(
                        "CallId"
                    ),
                    ptc=normalized_row.get(
                        "Ptc"
                    ),
                    event=normalized_row.get(
                        "Event"
                    ),
                    event_type=normalized_row.get(
                        "Type"
                    ),
                    information=normalized_row.get(
                        "Information"
                    ),
                    raw_fields=normalized_row,
                )
            )

        return rows

    @staticmethod
    def _normalize_row(
        raw_row: dict[str | None, str | list[str] | None],
    ) -> dict[str, str | None]:
        """
        Normalize a DictReader row.

        DictReader uses a None key when a row contains more values than
        the header. Such extra values are not silently accepted.
        """

        if None in raw_row:
            extra_values = raw_row[None]

            raise TraceParserError(
                "Trace row contains more values than the CSV header: "
                f"{extra_values}"
            )

        normalized_row: dict[str, str | None] = {}

        for key, value in raw_row.items():
            if key is None:
                continue

            normalized_key = key.strip()

            if not normalized_key:
                continue

            if isinstance(value, list):
                raise TraceParserError(
                    "Unexpected list value for trace column "
                    f"'{normalized_key}'"
                )

            normalized_row[normalized_key] = (
                value.strip()
                if value is not None
                else None
            )

        return normalized_row

    @staticmethod
    def _validate_header(
        fieldnames: list[str] | None,
    ) -> None:
        if not fieldnames:
            raise TraceParserError(
                "Trace CSV header is missing"
            )

        normalized_columns = {
            column.strip()
            for column in fieldnames
            if column and column.strip()
        }

        missing_columns = [
            column
            for column in EXPECTED_COLUMNS
            if column not in normalized_columns
        ]

        if missing_columns:
            raise TraceParserError(
                "Trace CSV is missing required columns: "
                + ", ".join(missing_columns)
            )

    @staticmethod
    def _parse_timestamp(
        value: str | None,
    ) -> datetime | None:
        if value is None:
            return None

        normalized_value = value.strip()

        if (
            not normalized_value
            or normalized_value.lower() == "<null>"
        ):
            return None

        for timestamp_format in TIMESTAMP_FORMATS:
            try:
                return datetime.strptime(
                    normalized_value,
                    timestamp_format,
                )
            except ValueError:
                continue

        return None

    @staticmethod
    def _validate_source(
        source: SourceArtifact,
    ) -> None:
        if source.artifact_type is not SourceArtifactType.TRACE:
            raise TraceParserError(
                "TraceParser accepts only TRACE source artifacts. "
                f"Received: {source.artifact_type}"
            )

        source_path = source.source_path

        if not isinstance(source_path, Path):
            raise TraceParserError(
                "Source artifact path must be a pathlib.Path"
            )

        if not source_path.exists():
            raise TraceParserError(
                f"Trace file was not found: {source_path}"
            )

        if not source_path.is_file():
            raise TraceParserError(
                f"Trace source is not a file: {source_path}"
            )
