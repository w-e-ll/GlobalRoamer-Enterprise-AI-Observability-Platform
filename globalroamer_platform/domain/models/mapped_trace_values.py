from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from globalroamer_platform.domain.models.mapping_definition import (
    MappingOperation,
    MappingSourceType,
    MappingValueType,
)


class MappingValueStatus(StrEnum):
    """Result status for one mapping definition."""

    MAPPED = "mapped"
    DEFAULTED = "defaulted"
    MISSING = "missing"
    CONVERSION_ERROR = "conversion_error"
    MAPPING_ERROR = "mapping_error"


@dataclass(frozen=True, slots=True)
class MappedValue:
    """
    Represent the result produced by one mapping definition.

    The model preserves enough provenance to explain how a final value
    was produced without retaining the complete mapping configuration.
    """

    name: str
    value: Any
    status: MappingValueStatus

    operation: MappingOperation
    value_type: MappingValueType

    source_type: MappingSourceType | None = None
    source_name: str | None = None
    source_value: Any = None
    source_line_number: int | None = None
    source_expression: str | None = None

    confidence: float = 1.0
    warning: str | None = None
    error: str | None = None

    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()

        if not normalized_name:
            raise ValueError(
                "Mapped value name must not be empty"
            )

        if not isinstance(
            self.status,
            MappingValueStatus,
        ):
            raise TypeError(
                "status must be a MappingValueStatus"
            )

        if not isinstance(
            self.operation,
            MappingOperation,
        ):
            raise TypeError(
                "operation must be a MappingOperation"
            )

        if not isinstance(
            self.value_type,
            MappingValueType,
        ):
            raise TypeError(
                "value_type must be a MappingValueType"
            )

        if (
            self.source_type is not None
            and not isinstance(
                self.source_type,
                MappingSourceType,
            )
        ):
            raise TypeError(
                "source_type must be a MappingSourceType"
            )

        if (
            self.source_line_number is not None
            and self.source_line_number <= 0
        ):
            raise ValueError(
                "source_line_number must be greater than zero"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "confidence must be between 0.0 and 1.0"
            )

        normalized_source_name = _normalize_optional_text(
            self.source_name
        )
        normalized_source_expression = _normalize_optional_text(
            self.source_expression
        )
        normalized_warning = _normalize_optional_text(
            self.warning
        )
        normalized_error = _normalize_optional_text(
            self.error
        )

        self._validate_status(
            warning=normalized_warning,
            error=normalized_error,
        )

        object.__setattr__(
            self,
            "name",
            normalized_name,
        )
        object.__setattr__(
            self,
            "source_name",
            normalized_source_name,
        )
        object.__setattr__(
            self,
            "source_expression",
            normalized_source_expression,
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
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(
                dict(self.metadata)
            ),
        )

    def _validate_status(
        self,
        *,
        warning: str | None,
        error: str | None,
    ) -> None:
        successful_statuses = {
            MappingValueStatus.MAPPED,
            MappingValueStatus.DEFAULTED,
        }
        error_statuses = {
            MappingValueStatus.CONVERSION_ERROR,
            MappingValueStatus.MAPPING_ERROR,
        }

        if (
            self.status in successful_statuses
            and self.value is None
        ):
            raise ValueError(
                f"Status '{self.status.value}' requires a value"
            )

        if (
            self.status is MappingValueStatus.MISSING
            and self.value is not None
        ):
            raise ValueError(
                "MISSING mapped value must not contain a value"
            )

        if self.status in error_statuses and error is None:
            raise ValueError(
                f"Status '{self.status.value}' requires an error"
            )

        if (
            self.status not in error_statuses
            and error is not None
        ):
            raise ValueError(
                f"Status '{self.status.value}' must not contain an error"
            )

        if (
            self.status is MappingValueStatus.DEFAULTED
            and warning is None
        ):
            raise ValueError(
                "DEFAULTED mapped value requires a warning explaining "
                "why the default was used"
            )

    @classmethod
    def mapped(
        cls,
        *,
        name: str,
        value: Any,
        operation: MappingOperation,
        value_type: MappingValueType,
        source_type: MappingSourceType | None = None,
        source_name: str | None = None,
        source_value: Any = None,
        source_line_number: int | None = None,
        source_expression: str | None = None,
        confidence: float = 1.0,
        warning: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MappedValue:
        return cls(
            name=name,
            value=value,
            status=MappingValueStatus.MAPPED,
            operation=operation,
            value_type=value_type,
            source_type=source_type,
            source_name=source_name,
            source_value=source_value,
            source_line_number=source_line_number,
            source_expression=source_expression,
            confidence=confidence,
            warning=warning,
            metadata=metadata or {},
        )

    @classmethod
    def defaulted(
        cls,
        *,
        name: str,
        value: Any,
        operation: MappingOperation,
        value_type: MappingValueType,
        reason: str,
        source_type: MappingSourceType | None = None,
        source_name: str | None = None,
        confidence: float = 1.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> MappedValue:
        return cls(
            name=name,
            value=value,
            status=MappingValueStatus.DEFAULTED,
            operation=operation,
            value_type=value_type,
            source_type=source_type,
            source_name=source_name,
            confidence=confidence,
            warning=reason,
            metadata=metadata or {},
        )

    @classmethod
    def missing(
        cls,
        *,
        name: str,
        operation: MappingOperation,
        value_type: MappingValueType,
        source_type: MappingSourceType | None = None,
        source_name: str | None = None,
        warning: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MappedValue:
        return cls(
            name=name,
            value=None,
            status=MappingValueStatus.MISSING,
            operation=operation,
            value_type=value_type,
            source_type=source_type,
            source_name=source_name,
            confidence=0.0,
            warning=warning,
            metadata=metadata or {},
        )

    @classmethod
    def conversion_error(
        cls,
        *,
        name: str,
        operation: MappingOperation,
        value_type: MappingValueType,
        source_value: Any,
        error: str,
        source_type: MappingSourceType | None = None,
        source_name: str | None = None,
        source_line_number: int | None = None,
        source_expression: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MappedValue:
        return cls(
            name=name,
            value=None,
            status=MappingValueStatus.CONVERSION_ERROR,
            operation=operation,
            value_type=value_type,
            source_type=source_type,
            source_name=source_name,
            source_value=source_value,
            source_line_number=source_line_number,
            source_expression=source_expression,
            confidence=0.0,
            error=error,
            metadata=metadata or {},
        )

    @classmethod
    def mapping_error(
        cls,
        *,
        name: str,
        operation: MappingOperation,
        value_type: MappingValueType,
        error: str,
        source_type: MappingSourceType | None = None,
        source_name: str | None = None,
        source_value: Any = None,
        source_line_number: int | None = None,
        source_expression: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MappedValue:
        return cls(
            name=name,
            value=None,
            status=MappingValueStatus.MAPPING_ERROR,
            operation=operation,
            value_type=value_type,
            source_type=source_type,
            source_name=source_name,
            source_value=source_value,
            source_line_number=source_line_number,
            source_expression=source_expression,
            confidence=0.0,
            error=error,
            metadata=metadata or {},
        )

    @property
    def is_successful(self) -> bool:
        return self.status in {
            MappingValueStatus.MAPPED,
            MappingValueStatus.DEFAULTED,
        }

    @property
    def is_error(self) -> bool:
        return self.status in {
            MappingValueStatus.CONVERSION_ERROR,
            MappingValueStatus.MAPPING_ERROR,
        }

    @property
    def is_missing(self) -> bool:
        return self.status is MappingValueStatus.MISSING

    @property
    def used_default(self) -> bool:
        return self.status is MappingValueStatus.DEFAULTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": _serialize_value(
                self.value
            ),
            "status": self.status.value,
            "operation": self.operation.value,
            "value_type": self.value_type.value,
            "source_type": (
                self.source_type.value
                if self.source_type is not None
                else None
            ),
            "source_name": self.source_name,
            "source_value": _serialize_value(
                self.source_value
            ),
            "source_line_number": self.source_line_number,
            "source_expression": self.source_expression,
            "confidence": self.confidence,
            "warning": self.warning,
            "error": self.error,
            "metadata": dict(
                self.metadata
            ),
        }


@dataclass(frozen=True, slots=True)
class MappedTraceValues:
    """
    Complete result of applying mapping definitions to one trace.

    Every configured target should have a corresponding MappedValue,
    including missing or failed results. This keeps mapping execution
    observable and prevents silent data loss.
    """

    values: Mapping[str, MappedValue]
    mapping_warnings: tuple[str, ...] = ()
    mapping_errors: tuple[str, ...] = ()
    configuration_version: str | None = None

    def __post_init__(self) -> None:
        normalized_values: dict[str, MappedValue] = {}

        for key, mapped_value in self.values.items():
            normalized_key = key.strip()

            if not normalized_key:
                raise ValueError(
                    "Mapped value mapping contains an empty key"
                )

            if not isinstance(
                mapped_value,
                MappedValue,
            ):
                raise TypeError(
                    "MappedTraceValues values must be MappedValue "
                    "instances"
                )

            if normalized_key != mapped_value.name:
                raise ValueError(
                    "Mapped value key must match its name: "
                    f"'{normalized_key}' != '{mapped_value.name}'"
                )

            normalized_values[normalized_key] = mapped_value

        object.__setattr__(
            self,
            "values",
            MappingProxyType(
                normalized_values
            ),
        )
        object.__setattr__(
            self,
            "mapping_warnings",
            _normalize_messages(
                self.mapping_warnings
            ),
        )
        object.__setattr__(
            self,
            "mapping_errors",
            _normalize_messages(
                self.mapping_errors
            ),
        )
        object.__setattr__(
            self,
            "configuration_version",
            _normalize_optional_text(
                self.configuration_version
            ),
        )

    @classmethod
    def empty(
        cls,
        *,
        configuration_version: str | None = None,
    ) -> MappedTraceValues:
        return cls(
            values={},
            configuration_version=configuration_version,
        )

    @classmethod
    def create(
        cls,
        *,
        values: Mapping[str, MappedValue] | None = None,
        mapping_warnings: tuple[str, ...] = (),
        mapping_errors: tuple[str, ...] = (),
        configuration_version: str | None = None,
    ) -> MappedTraceValues:
        return cls(
            values=values or {},
            mapping_warnings=mapping_warnings,
            mapping_errors=mapping_errors,
            configuration_version=configuration_version,
        )

    def get(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        """
        Return a successful mapped value.

        Missing and failed mapping results return the supplied default.
        """

        mapped_value = self.values.get(
            name
        )

        if (
            mapped_value is None
            or not mapped_value.is_successful
        ):
            return default

        return mapped_value.value

    def get_entry(
        self,
        name: str,
    ) -> MappedValue | None:
        return self.values.get(name)

    def contains(
        self,
        name: str,
    ) -> bool:
        return name in self.values

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.values.keys())

    @property
    def count(self) -> int:
        return len(self.values)

    @property
    def successful_count(self) -> int:
        return sum(
            mapped_value.is_successful
            for mapped_value in self.values.values()
        )

    @property
    def missing_count(self) -> int:
        return sum(
            mapped_value.is_missing
            for mapped_value in self.values.values()
        )

    @property
    def error_count(self) -> int:
        return sum(
            mapped_value.is_error
            for mapped_value in self.values.values()
        )

    @property
    def defaulted_count(self) -> int:
        return sum(
            mapped_value.used_default
            for mapped_value in self.values.values()
        )

    @property
    def has_errors(self) -> bool:
        return bool(
            self.mapping_errors
            or self.error_count
        )

    @property
    def has_warnings(self) -> bool:
        return bool(
            self.mapping_warnings
            or self.defaulted_count
        )

    @property
    def is_complete(self) -> bool:
        return (
            self.count > 0
            and self.missing_count == 0
            and self.error_count == 0
        )

    def to_value_dict(
        self,
        *,
        include_defaults: bool = True,
    ) -> dict[str, Any]:
        """Return only successfully mapped values."""

        return {
            name: mapped_value.value
            for name, mapped_value in self.values.items()
            if mapped_value.is_successful
            and (
                include_defaults
                or not mapped_value.used_default
            )
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": {
                name: mapped_value.to_dict()
                for name, mapped_value in self.values.items()
            },
            "mapping_warnings": list(
                self.mapping_warnings
            ),
            "mapping_errors": list(
                self.mapping_errors
            ),
            "configuration_version": (
                self.configuration_version
            ),
            "summary": {
                "total": self.count,
                "successful": self.successful_count,
                "defaulted": self.defaulted_count,
                "missing": self.missing_count,
                "errors": self.error_count,
                "complete": self.is_complete,
            },
        }


def _normalize_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized_value = value.strip()

    return normalized_value or None


def _normalize_messages(
    messages: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        message.strip()
        for message in messages
        if message and message.strip()
    )


def _serialize_value(
    value: Any,
) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Mapping):
        return {
            str(key): _serialize_value(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return [
            _serialize_value(item)
            for item in value
        ]

    if isinstance(value, list):
        return [
            _serialize_value(item)
            for item in value
        ]

    return value
