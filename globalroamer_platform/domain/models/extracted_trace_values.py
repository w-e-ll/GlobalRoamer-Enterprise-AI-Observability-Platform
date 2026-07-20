from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ExtractedValue:
    """
    Represent one value extracted from trace content.

    The value retains its source location and extraction method so later
    normalization remains auditable.
    """

    name: str
    value: Any

    source_line_number: int | None = None
    source_expression: str | None = None
    extraction_method: str = "assignment"

    confidence: float = 1.0
    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()

        if not normalized_name:
            raise ValueError(
                "Extracted value name must not be empty"
            )

        if self.value is None:
            raise ValueError(
                f"Extracted value '{normalized_name}' must not be None"
            )

        if (
            self.source_line_number is not None
            and self.source_line_number <= 0
        ):
            raise ValueError(
                "source_line_number must be greater than zero"
            )

        normalized_expression = _normalize_optional_text(
            self.source_expression
        )
        normalized_method = self.extraction_method.strip().casefold()

        if not normalized_method:
            raise ValueError(
                "Extraction method must not be empty"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "Confidence must be between 0.0 and 1.0"
            )

        object.__setattr__(
            self,
            "name",
            normalized_name,
        )
        object.__setattr__(
            self,
            "source_expression",
            normalized_expression,
        )
        object.__setattr__(
            self,
            "extraction_method",
            normalized_method,
        )
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(
                dict(self.metadata)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": _serialize_value(self.value),
            "source_line_number": self.source_line_number,
            "source_expression": self.source_expression,
            "extraction_method": self.extraction_method,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ExtractedTraceValues:
    """
    Collection of values extracted from one raw trace.

    This model contains values as they were found in the trace. It does
    not apply telecom mappings or final normalization.
    """

    values: Mapping[str, ExtractedValue]
    extraction_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized_values: dict[str, ExtractedValue] = {}

        for key, extracted_value in self.values.items():
            normalized_key = key.strip()

            if not normalized_key:
                raise ValueError(
                    "Extracted value mapping contains an empty key"
                )

            if not isinstance(
                extracted_value,
                ExtractedValue,
            ):
                raise TypeError(
                    "ExtractedTraceValues values must be "
                    "ExtractedValue instances"
                )

            if normalized_key != extracted_value.name:
                raise ValueError(
                    "Extracted value mapping key must match its name: "
                    f"'{normalized_key}' != "
                    f"'{extracted_value.name}'"
                )

            normalized_values[normalized_key] = extracted_value

        normalized_warnings = tuple(
            warning.strip()
            for warning in self.extraction_warnings
            if warning and warning.strip()
        )

        object.__setattr__(
            self,
            "values",
            MappingProxyType(
                normalized_values
            ),
        )
        object.__setattr__(
            self,
            "extraction_warnings",
            normalized_warnings,
        )

    @classmethod
    def empty(cls) -> ExtractedTraceValues:
        """Create an empty extraction result."""

        return cls(
            values={},
            extraction_warnings=(),
        )

    @classmethod
    def create(
        cls,
        *,
        values: Mapping[str, ExtractedValue] | None = None,
        extraction_warnings: tuple[str, ...] = (),
    ) -> ExtractedTraceValues:
        return cls(
            values=values or {},
            extraction_warnings=extraction_warnings,
        )

    def get(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        """Return the raw value of an extracted field."""

        extracted_value = self.values.get(
            name
        )

        if extracted_value is None:
            return default

        return extracted_value.value

    def get_entry(
        self,
        name: str,
    ) -> ExtractedValue | None:
        """Return the complete extracted-value record."""

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
    def is_empty(self) -> bool:
        return not self.values

    @property
    def has_warnings(self) -> bool:
        return bool(self.extraction_warnings)

    def to_value_dict(self) -> dict[str, Any]:
        """
        Return only extracted names and values.

        This provides a compatibility representation similar to the old
        ``extracted_values`` dictionary.
        """

        return {
            name: extracted_value.value
            for name, extracted_value in self.values.items()
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": {
                name: extracted_value.to_dict()
                for name, extracted_value in self.values.items()
            },
            "extraction_warnings": list(
                self.extraction_warnings
            ),
        }


def _normalize_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized_value = value.strip()

    return normalized_value or None


def _serialize_value(
    value: Any,
) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Mapping):
        return {
            key: _serialize_value(item)
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
