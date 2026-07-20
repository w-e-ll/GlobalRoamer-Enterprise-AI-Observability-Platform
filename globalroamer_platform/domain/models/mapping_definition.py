from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class MappingSourceType(StrEnum):
    """Source inspected by a mapping rule."""

    EXTRACTED_VALUE = "extracted_value"
    INFORMATION = "information"
    EVENT = "event"
    EVENT_TYPE = "event_type"
    RAW_FIELD = "raw_field"
    TRACE_TEXT = "trace_text"


class MappingOperation(StrEnum):
    """Operation used to obtain the mapped value."""

    COPY = "copy"
    REGEX = "regex"
    LOOKUP = "lookup"
    CONSTANT = "constant"


class MappingValueType(StrEnum):
    """Optional target-value conversion."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"


class MappingDuplicateStrategy(StrEnum):
    """Resolution strategy when a rule produces multiple values."""

    FIRST = "first"
    LAST = "last"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class MappingDefinition:
    """
    Describe one configuration-driven trace mapping rule.

    A definition identifies where the input comes from, how the value
    should be obtained, and under which target name it should be stored.

    This object contains validated configuration only. It does not inspect
    traces or perform the mapping itself.
    """

    target_name: str
    operation: MappingOperation

    source_type: MappingSourceType | None = None
    source_name: str | None = None

    pattern: str | None = None
    group: str | int | None = None

    lookup_values: Mapping[str, Any] = MappingProxyType({})
    constant_value: Any = None

    value_type: MappingValueType = MappingValueType.STRING
    required: bool = False
    default_value: Any = None

    duplicate_strategy: MappingDuplicateStrategy = (
        MappingDuplicateStrategy.FIRST
    )

    case_sensitive: bool = False
    strip_value: bool = True
    confidence: float = 1.0

    description: str | None = None
    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        normalized_target_name = self.target_name.strip()

        if not normalized_target_name:
            raise ValueError(
                "Mapping target_name must not be empty"
            )

        if not isinstance(
            self.operation,
            MappingOperation,
        ):
            raise TypeError(
                "operation must be a MappingOperation"
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

        if not isinstance(
            self.value_type,
            MappingValueType,
        ):
            raise TypeError(
                "value_type must be a MappingValueType"
            )

        if not isinstance(
            self.duplicate_strategy,
            MappingDuplicateStrategy,
        ):
            raise TypeError(
                "duplicate_strategy must be a "
                "MappingDuplicateStrategy"
            )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "Mapping confidence must be between 0.0 and 1.0"
            )

        normalized_source_name = _normalize_optional_text(
            self.source_name
        )
        normalized_pattern = _normalize_optional_text(
            self.pattern
        )
        normalized_description = _normalize_optional_text(
            self.description
        )

        self._validate_operation_configuration(
            source_name=normalized_source_name,
            pattern=normalized_pattern,
        )

        if normalized_pattern is not None:
            flags = (
                0
                if self.case_sensitive
                else re.IGNORECASE
            )

            try:
                re.compile(
                    normalized_pattern,
                    flags,
                )
            except re.error as exc:
                raise ValueError(
                    f"Invalid regex for mapping "
                    f"'{normalized_target_name}': {exc}"
                ) from exc

        normalized_lookup_values = {
            str(key): value
            for key, value in self.lookup_values.items()
        }

        object.__setattr__(
            self,
            "target_name",
            normalized_target_name,
        )
        object.__setattr__(
            self,
            "source_name",
            normalized_source_name,
        )
        object.__setattr__(
            self,
            "pattern",
            normalized_pattern,
        )
        object.__setattr__(
            self,
            "description",
            normalized_description,
        )
        object.__setattr__(
            self,
            "lookup_values",
            MappingProxyType(
                normalized_lookup_values
            ),
        )
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(
                dict(self.metadata)
            ),
        )

    def _validate_operation_configuration(
        self,
        *,
        source_name: str | None,
        pattern: str | None,
    ) -> None:
        if self.operation is MappingOperation.CONSTANT:
            if self.constant_value is None:
                raise ValueError(
                    "CONSTANT mapping requires constant_value"
                )

            if self.source_type is not None:
                raise ValueError(
                    "CONSTANT mapping must not define source_type"
                )

            if source_name is not None:
                raise ValueError(
                    "CONSTANT mapping must not define source_name"
                )

            if pattern is not None:
                raise ValueError(
                    "CONSTANT mapping must not define pattern"
                )

            return

        if self.source_type is None:
            raise ValueError(
                f"{self.operation.value.upper()} mapping requires "
                "source_type"
            )

        if self.source_type in {
            MappingSourceType.EXTRACTED_VALUE,
            MappingSourceType.RAW_FIELD,
        } and source_name is None:
            raise ValueError(
                f"Source type '{self.source_type.value}' requires "
                "source_name"
            )

        if self.operation is MappingOperation.REGEX:
            if pattern is None:
                raise ValueError(
                    "REGEX mapping requires pattern"
                )

        elif pattern is not None:
            raise ValueError(
                f"{self.operation.value.upper()} mapping must not "
                "define pattern"
            )

        if self.operation is MappingOperation.LOOKUP:
            if not self.lookup_values:
                raise ValueError(
                    "LOOKUP mapping requires lookup_values"
                )

        elif self.lookup_values:
            raise ValueError(
                f"{self.operation.value.upper()} mapping must not "
                "define lookup_values"
            )

        if (
            self.operation is not MappingOperation.REGEX
            and self.group is not None
        ):
            raise ValueError(
                "Regex group may only be configured for REGEX mappings"
            )

    @property
    def is_regex(self) -> bool:
        return self.operation is MappingOperation.REGEX

    @property
    def is_constant(self) -> bool:
        return self.operation is MappingOperation.CONSTANT

    @property
    def has_default(self) -> bool:
        return self.default_value is not None

    def compile_pattern(self) -> re.Pattern[str] | None:
        """
        Compile and return the configured regex.

        Compilation stays out of the stored dataclass state so the model
        remains simple to serialize and safe to construct from YAML.
        """

        if self.pattern is None:
            return None

        flags = (
            0
            if self.case_sensitive
            else re.IGNORECASE
        )

        return re.compile(
            self.pattern,
            flags,
        )

    def normalize_lookup_key(
        self,
        value: Any,
    ) -> str:
        """Normalize a candidate value for lookup matching."""

        normalized = str(value)

        if self.strip_value:
            normalized = normalized.strip()

        if not self.case_sensitive:
            normalized = normalized.casefold()

        return normalized

    def normalized_lookup_values(
        self,
    ) -> Mapping[str, Any]:
        """
        Return lookup values with keys normalized according to the rule.

        The original immutable configuration remains unchanged.
        """

        return MappingProxyType(
            {
                self.normalize_lookup_key(key): value
                for key, value in self.lookup_values.items()
            }
        )

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
    ) -> MappingDefinition:
        """
        Construct a definition from parsed YAML or JSON configuration.

        Enum fields may be supplied as their string values.
        """

        try:
            operation = MappingOperation(
                data["operation"]
            )
        except KeyError as exc:
            raise ValueError(
                "Mapping definition requires 'operation'"
            ) from exc

        try:
            target_name = str(
                data["target_name"]
            )
        except KeyError as exc:
            raise ValueError(
                "Mapping definition requires 'target_name'"
            ) from exc

        source_type_value = data.get(
            "source_type"
        )
        value_type_value = data.get(
            "value_type",
            MappingValueType.STRING.value,
        )
        duplicate_strategy_value = data.get(
            "duplicate_strategy",
            MappingDuplicateStrategy.FIRST.value,
        )

        return cls(
            target_name=target_name,
            operation=operation,
            source_type=(
                MappingSourceType(
                    source_type_value
                )
                if source_type_value is not None
                else None
            ),
            source_name=data.get(
                "source_name"
            ),
            pattern=data.get(
                "pattern"
            ),
            group=data.get(
                "group"
            ),
            lookup_values=data.get(
                "lookup_values",
                {},
            ),
            constant_value=data.get(
                "constant_value"
            ),
            value_type=MappingValueType(
                value_type_value
            ),
            required=bool(
                data.get(
                    "required",
                    False,
                )
            ),
            default_value=data.get(
                "default_value"
            ),
            duplicate_strategy=MappingDuplicateStrategy(
                duplicate_strategy_value
            ),
            case_sensitive=bool(
                data.get(
                    "case_sensitive",
                    False,
                )
            ),
            strip_value=bool(
                data.get(
                    "strip_value",
                    True,
                )
            ),
            confidence=float(
                data.get(
                    "confidence",
                    1.0,
                )
            ),
            description=data.get(
                "description"
            ),
            metadata=data.get(
                "metadata",
                {},
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_name": self.target_name,
            "operation": self.operation.value,
            "source_type": (
                self.source_type.value
                if self.source_type is not None
                else None
            ),
            "source_name": self.source_name,
            "pattern": self.pattern,
            "group": self.group,
            "lookup_values": dict(
                self.lookup_values
            ),
            "constant_value": self.constant_value,
            "value_type": self.value_type.value,
            "required": self.required,
            "default_value": self.default_value,
            "duplicate_strategy": (
                self.duplicate_strategy.value
            ),
            "case_sensitive": self.case_sensitive,
            "strip_value": self.strip_value,
            "confidence": self.confidence,
            "description": self.description,
            "metadata": dict(
                self.metadata
            ),
        }


@dataclass(frozen=True, slots=True)
class MappingConfiguration:
    """Validated collection of mapping definitions."""

    definitions: tuple[MappingDefinition, ...]
    version: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.definitions:
            raise ValueError(
                "MappingConfiguration requires at least one definition"
            )

        target_names: set[str] = set()

        for definition in self.definitions:
            if not isinstance(
                definition,
                MappingDefinition,
            ):
                raise TypeError(
                    "definitions must contain MappingDefinition objects"
                )

            if definition.target_name in target_names:
                raise ValueError(
                    "Duplicate mapping target_name: "
                    f"'{definition.target_name}'"
                )

            target_names.add(
                definition.target_name
            )

        object.__setattr__(
            self,
            "version",
            _normalize_optional_text(
                self.version
            ),
        )
        object.__setattr__(
            self,
            "description",
            _normalize_optional_text(
                self.description
            ),
        )

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
    ) -> MappingConfiguration:
        raw_definitions = data.get(
            "mappings"
        )

        if not isinstance(
            raw_definitions,
            list,
        ):
            raise ValueError(
                "Mapping configuration requires a 'mappings' list"
            )

        return cls(
            definitions=tuple(
                MappingDefinition.from_dict(
                    item
                )
                for item in raw_definitions
            ),
            version=data.get(
                "version"
            ),
            description=data.get(
                "description"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "description": self.description,
            "mappings": [
                definition.to_dict()
                for definition in self.definitions
            ],
        }


def _normalize_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized_value = value.strip()

    return normalized_value or None
