from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone, tzinfo
from enum import StrEnum
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from globalroamer_platform.domain.models.mapped_trace_values import (
    MappedTraceValues,
    MappedValue,
    MappingValueStatus,
)
from globalroamer_platform.domain.models.mapping_definition import (
    MappingValueType,
)
from globalroamer_platform.domain.models.raw_trace import (
    RawTrace,
    RawTraceRow,
)


class NaiveDatetimeStrategy(StrEnum):
    """
    Define how datetimes without timezone information are interpreted.
    """

    ASSUME_SOURCE_TIMEZONE = "assume_source_timezone"
    ASSUME_UTC = "assume_utc"
    REJECT = "reject"


class TimeNormalizationStatus(StrEnum):
    """Outcome of normalizing one timestamp."""

    NORMALIZED = "normalized"
    UNCHANGED = "unchanged"
    MISSING = "missing"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class TimeNormalizationResult:
    """
    Result of normalizing one timestamp.

    The original value is retained for diagnostics and auditability.
    """

    original_value: datetime | str | None
    normalized_value: datetime | None
    status: TimeNormalizationStatus
    source_timezone: str | None = None
    target_timezone: str = "UTC"
    warning: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.status,
            TimeNormalizationStatus,
        ):
            raise TypeError(
                "status must be a TimeNormalizationStatus"
            )

        normalized_warning = _normalize_optional_text(
            self.warning
        )
        normalized_error = _normalize_optional_text(
            self.error
        )

        if (
            self.status
            in {
                TimeNormalizationStatus.NORMALIZED,
                TimeNormalizationStatus.UNCHANGED,
            }
            and self.normalized_value is None
        ):
            raise ValueError(
                f"Status '{self.status.value}' requires "
                "normalized_value"
            )

        if (
            self.status is TimeNormalizationStatus.MISSING
            and self.original_value is not None
        ):
            raise ValueError(
                "MISSING result must have original_value=None"
            )

        if (
            self.status is TimeNormalizationStatus.INVALID
            and normalized_error is None
        ):
            raise ValueError(
                "INVALID result requires an error"
            )

        if (
            self.status is not TimeNormalizationStatus.INVALID
            and normalized_error is not None
        ):
            raise ValueError(
                f"Status '{self.status.value}' must not contain "
                "an error"
            )

        object.__setattr__(
            self,
            "warning",
            normalized_warning,
        )
        object.__setattr__(
            self,
            "error",
            normalized_error,
        )

    @property
    def is_successful(self) -> bool:
        return self.status in {
            TimeNormalizationStatus.NORMALIZED,
            TimeNormalizationStatus.UNCHANGED,
        }


@dataclass(frozen=True, slots=True)
class NormalizedTraceResult:
    """
    Result of normalizing timestamps in RawTrace rows.
    """

    trace: RawTrace
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


class TimeNormalizer:
    """
    Normalize trace timestamps into one target timezone.

    The normalizer:

    - accepts datetime objects and ISO-8601 strings;
    - handles timestamps ending in ``Z``;
    - assigns a configured timezone to naive datetimes;
    - converts aware datetimes to the configured target timezone;
    - can normalize RawTrace row timestamps;
    - can normalize successful DATETIME values in MappedTraceValues.

    It does not:

    - infer timezones from geographic or telecom identifiers;
    - reorder trace rows;
    - calculate durations;
    - modify source objects in place.
    """

    DEFAULT_TARGET_TIMEZONE: Final[str] = "UTC"

    def __init__(
        self,
        *,
        source_timezone: str | tzinfo = "UTC",
        target_timezone: str | tzinfo = "UTC",
        naive_strategy: NaiveDatetimeStrategy = (
            NaiveDatetimeStrategy.ASSUME_SOURCE_TIMEZONE
        ),
    ) -> None:
        if not isinstance(
            naive_strategy,
            NaiveDatetimeStrategy,
        ):
            raise TypeError(
                "naive_strategy must be a NaiveDatetimeStrategy"
            )

        self._source_timezone = self._resolve_timezone(
            source_timezone
        )
        self._target_timezone = self._resolve_timezone(
            target_timezone
        )
        self._source_timezone_name = self._timezone_name(
            source_timezone,
            self._source_timezone,
        )
        self._target_timezone_name = self._timezone_name(
            target_timezone,
            self._target_timezone,
        )
        self._naive_strategy = naive_strategy

    @property
    def source_timezone_name(self) -> str:
        return self._source_timezone_name

    @property
    def target_timezone_name(self) -> str:
        return self._target_timezone_name

    @property
    def naive_strategy(self) -> NaiveDatetimeStrategy:
        return self._naive_strategy

    def normalize(
        self,
        value: datetime | str | None,
    ) -> TimeNormalizationResult:
        """
        Normalize one datetime value.

        Invalid input is represented as a result instead of raising,
        allowing callers to continue processing the remaining trace.
        """

        if value is None:
            return TimeNormalizationResult(
                original_value=None,
                normalized_value=None,
                status=TimeNormalizationStatus.MISSING,
                source_timezone=self._source_timezone_name,
                target_timezone=self._target_timezone_name,
            )

        try:
            parsed_value = self._parse_datetime(
                value
            )
        except (TypeError, ValueError) as exc:
            return TimeNormalizationResult(
                original_value=value,
                normalized_value=None,
                status=TimeNormalizationStatus.INVALID,
                source_timezone=self._source_timezone_name,
                target_timezone=self._target_timezone_name,
                error=str(exc),
            )

        warning: str | None = None

        if self._is_naive(parsed_value):
            try:
                parsed_value, warning = (
                    self._apply_naive_strategy(
                        parsed_value
                    )
                )
            except ValueError as exc:
                return TimeNormalizationResult(
                    original_value=value,
                    normalized_value=None,
                    status=TimeNormalizationStatus.INVALID,
                    source_timezone=self._source_timezone_name,
                    target_timezone=self._target_timezone_name,
                    error=str(exc),
                )

        normalized_value = parsed_value.astimezone(
            self._target_timezone
        )

        status = (
            TimeNormalizationStatus.UNCHANGED
            if normalized_value == parsed_value
            and parsed_value.tzinfo == self._target_timezone
            else TimeNormalizationStatus.NORMALIZED
        )

        return TimeNormalizationResult(
            original_value=value,
            normalized_value=normalized_value,
            status=status,
            source_timezone=self._source_timezone_name,
            target_timezone=self._target_timezone_name,
            warning=warning,
        )

    def normalize_or_raise(
        self,
        value: datetime | str,
    ) -> datetime:
        """
        Normalize one value and raise ValueError when it is invalid.
        """

        result = self.normalize(value)

        if not result.is_successful:
            raise ValueError(
                result.error
                or "Timestamp could not be normalized"
            )

        assert result.normalized_value is not None

        return result.normalized_value

    def normalize_trace(
        self,
        trace: RawTrace,
    ) -> NormalizedTraceResult:
        """
        Return a new RawTrace with normalized row timestamps.

        Rows with missing timestamps remain unchanged. Rows with invalid
        timestamps are also retained and reported as errors.
        """

        normalized_rows: list[RawTraceRow] = []
        warnings: list[str] = []
        errors: list[str] = []

        for row in trace.rows:
            result = self.normalize(
                row.timestamp
            )

            if result.status is TimeNormalizationStatus.MISSING:
                normalized_rows.append(row)
                continue

            if result.status is TimeNormalizationStatus.INVALID:
                errors.append(
                    f"Line {row.line_number}: {result.error}"
                )
                normalized_rows.append(row)
                continue

            if result.warning:
                warnings.append(
                    f"Line {row.line_number}: {result.warning}"
                )

            normalized_rows.append(
                replace(
                    row,
                    timestamp=result.normalized_value,
                )
            )

        normalized_trace = replace(
            trace,
            rows=tuple(normalized_rows),
            parser_warnings=(
                tuple(trace.parser_warnings)
                + tuple(warnings)
                + tuple(errors)
            ),
        )

        return NormalizedTraceResult(
            trace=normalized_trace,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    def normalize_mapped_values(
        self,
        mapped_values: MappedTraceValues,
    ) -> MappedTraceValues:
        """
        Normalize successful mapped values configured as DATETIME.

        Failed, missing and non-datetime mappings are returned unchanged.
        A failed time normalization converts the entry to a
        CONVERSION_ERROR result.
        """

        normalized_values: dict[str, MappedValue] = {}
        warnings = list(
            mapped_values.mapping_warnings
        )
        errors = list(
            mapped_values.mapping_errors
        )

        for name, mapped_value in mapped_values.values.items():
            if not self._should_normalize_mapped_value(
                mapped_value
            ):
                normalized_values[name] = mapped_value
                continue

            result = self.normalize(
                mapped_value.value
            )

            if result.is_successful:
                assert result.normalized_value is not None

                entry_warning = self._combine_messages(
                    mapped_value.warning,
                    result.warning,
                )

                normalized_values[name] = replace(
                    mapped_value,
                    value=result.normalized_value,
                    warning=entry_warning,
                    metadata={
                        **dict(mapped_value.metadata),
                        "time_normalized": True,
                        "target_timezone": (
                            self._target_timezone_name
                        ),
                    },
                )

                if result.warning:
                    warnings.append(
                        f"{name}: {result.warning}"
                    )

                continue

            error = (
                result.error
                or "Datetime normalization failed"
            )

            normalized_values[name] = replace(
                mapped_value,
                value=None,
                status=(
                    MappingValueStatus.CONVERSION_ERROR
                ),
                confidence=0.0,
                error=error,
                warning=None,
                metadata={
                    **dict(mapped_value.metadata),
                    "time_normalized": False,
                    "target_timezone": (
                        self._target_timezone_name
                    ),
                },
            )
            errors.append(
                f"{name}: {error}"
            )

        return MappedTraceValues.create(
            values=normalized_values,
            mapping_warnings=tuple(warnings),
            mapping_errors=tuple(errors),
            configuration_version=(
                mapped_values.configuration_version
            ),
        )

    @staticmethod
    def _should_normalize_mapped_value(
        mapped_value: MappedValue,
    ) -> bool:
        return (
            mapped_value.is_successful
            and mapped_value.value_type
            is MappingValueType.DATETIME
        )

    def _apply_naive_strategy(
        self,
        value: datetime,
    ) -> tuple[datetime, str]:
        if (
            self._naive_strategy
            is NaiveDatetimeStrategy.REJECT
        ):
            raise ValueError(
                f"Naive datetime {value!r} is not allowed"
            )

        if (
            self._naive_strategy
            is NaiveDatetimeStrategy.ASSUME_UTC
        ):
            return (
                value.replace(
                    tzinfo=timezone.utc
                ),
                "Naive datetime was interpreted as UTC",
            )

        return (
            value.replace(
                tzinfo=self._source_timezone
            ),
            (
                "Naive datetime was interpreted using source "
                f"timezone '{self._source_timezone_name}'"
            ),
        )

    @staticmethod
    def _parse_datetime(
        value: datetime | str,
    ) -> datetime:
        if isinstance(value, datetime):
            return value

        if not isinstance(value, str):
            raise TypeError(
                "Timestamp must be a datetime, ISO-8601 string, "
                f"or None; received {type(value).__name__}"
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Timestamp string must not be empty"
            )

        if normalized.endswith(
            (
                "Z",
                "z",
            )
        ):
            normalized = (
                normalized[:-1]
                + "+00:00"
            )

        try:
            return datetime.fromisoformat(
                normalized
            )
        except ValueError as exc:
            raise ValueError(
                f"Unsupported timestamp format: {value!r}"
            ) from exc

    @staticmethod
    def _is_naive(
        value: datetime,
    ) -> bool:
        return (
            value.tzinfo is None
            or value.utcoffset() is None
        )

    @staticmethod
    def _resolve_timezone(
        value: str | tzinfo,
    ) -> tzinfo:
        if isinstance(value, str):
            normalized = value.strip()

            if not normalized:
                raise ValueError(
                    "Timezone name must not be empty"
                )

            if normalized.upper() in {
                "UTC",
                "Z",
            }:
                return timezone.utc

            try:
                return ZoneInfo(
                    normalized
                )
            except ZoneInfoNotFoundError as exc:
                raise ValueError(
                    f"Unknown timezone: {value!r}"
                ) from exc

        if not isinstance(value, tzinfo):
            raise TypeError(
                "Timezone must be an IANA timezone name or "
                "datetime.tzinfo instance"
            )

        return value

    @staticmethod
    def _timezone_name(
        configured_value: str | tzinfo,
        resolved_value: tzinfo,
    ) -> str:
        if isinstance(configured_value, str):
            normalized = configured_value.strip()

            if normalized.upper() in {
                "UTC",
                "Z",
            }:
                return "UTC"

            return normalized

        timezone_key = getattr(
            resolved_value,
            "key",
            None,
        )

        if timezone_key:
            return str(timezone_key)

        timezone_name = resolved_value.tzname(
            datetime.now()
        )

        return timezone_name or str(
            resolved_value
        )

    @staticmethod
    def _combine_messages(
        first: str | None,
        second: str | None,
    ) -> str | None:
        messages = tuple(
            message.strip()
            for message in (
                first,
                second,
            )
            if message and message.strip()
        )

        if not messages:
            return None

        return "; ".join(messages)


def _normalize_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    return normalized or None
