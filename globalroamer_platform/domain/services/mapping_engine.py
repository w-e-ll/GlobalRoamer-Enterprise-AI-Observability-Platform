from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from globalroamer_platform.domain.models.extracted_trace_values import (
    ExtractedTraceValues,
)
from globalroamer_platform.domain.models.mapped_trace_values import (
    MappedTraceValues,
    MappedValue,
)
from globalroamer_platform.domain.models.mapping_definition import (
    MappingConfiguration,
    MappingDefinition,
    MappingDuplicateStrategy,
    MappingOperation,
    MappingSourceType,
    MappingValueType,
)
from globalroamer_platform.domain.models.raw_trace import (
    RawTrace,
    RawTraceRow,
)


@dataclass(frozen=True, slots=True)
class MappingCandidate:
    """
    Represent one source value available to a mapping definition.

    A source may produce several candidates because a trace contains
    multiple rows. Candidate selection is controlled by the mapping
    definition's duplicate strategy.
    """

    value: Any
    source_line_number: int | None = None
    source_expression: str | None = None
    source_column: str | None = None


class MappingEngine:
    """
    Apply validated mapping definitions to parsed trace data.

    The engine:

    - resolves mapping sources;
    - performs COPY, REGEX, LOOKUP and CONSTANT operations;
    - converts values to configured target types;
    - records missing values, defaults and errors;
    - preserves source provenance;
    - returns one result for every configured target.

    It does not load YAML files or mutate source models.
    """

    def map(
        self,
        *,
        trace: RawTrace,
        extracted_values: ExtractedTraceValues,
        configuration: MappingConfiguration,
    ) -> MappedTraceValues:
        mapped_values: dict[str, MappedValue] = {}
        warnings: list[str] = []
        errors: list[str] = []

        for definition in configuration.definitions:
            result = self._apply_definition(
                definition=definition,
                trace=trace,
                extracted_values=extracted_values,
            )

            mapped_values[result.name] = result

            if result.warning:
                warnings.append(
                    f"{result.name}: {result.warning}"
                )

            if result.error:
                errors.append(
                    f"{result.name}: {result.error}"
                )

        return MappedTraceValues.create(
            values=mapped_values,
            mapping_warnings=tuple(warnings),
            mapping_errors=tuple(errors),
            configuration_version=configuration.version,
        )

    def _apply_definition(
        self,
        *,
        definition: MappingDefinition,
        trace: RawTrace,
        extracted_values: ExtractedTraceValues,
    ) -> MappedValue:
        try:
            candidates = self._execute_operation(
                definition=definition,
                trace=trace,
                extracted_values=extracted_values,
            )
        except Exception as exc:
            return MappedValue.mapping_error(
                name=definition.target_name,
                operation=definition.operation,
                value_type=definition.value_type,
                source_type=definition.source_type,
                source_name=definition.source_name,
                error=str(exc),
                metadata=definition.metadata,
            )

        if not candidates:
            return self._handle_missing_value(
                definition
            )

        try:
            candidate, warning = self._select_candidate(
                definition=definition,
                candidates=candidates,
            )
        except ValueError as exc:
            return MappedValue.mapping_error(
                name=definition.target_name,
                operation=definition.operation,
                value_type=definition.value_type,
                source_type=definition.source_type,
                source_name=definition.source_name,
                error=str(exc),
                metadata=definition.metadata,
            )

        try:
            converted_value = self._convert_value(
                value=candidate.value,
                value_type=definition.value_type,
                strip_value=definition.strip_value,
            )
        except (TypeError, ValueError) as exc:
            return MappedValue.conversion_error(
                name=definition.target_name,
                operation=definition.operation,
                value_type=definition.value_type,
                source_type=definition.source_type,
                source_name=definition.source_name,
                source_value=candidate.value,
                source_line_number=candidate.source_line_number,
                source_expression=candidate.source_expression,
                error=str(exc),
                metadata={
                    **dict(definition.metadata),
                    "source_column": candidate.source_column,
                },
            )

        return MappedValue.mapped(
            name=definition.target_name,
            value=converted_value,
            operation=definition.operation,
            value_type=definition.value_type,
            source_type=definition.source_type,
            source_name=definition.source_name,
            source_value=candidate.value,
            source_line_number=candidate.source_line_number,
            source_expression=candidate.source_expression,
            confidence=definition.confidence,
            warning=warning,
            metadata={
                **dict(definition.metadata),
                "source_column": candidate.source_column,
            },
        )

    def _execute_operation(
        self,
        *,
        definition: MappingDefinition,
        trace: RawTrace,
        extracted_values: ExtractedTraceValues,
    ) -> tuple[MappingCandidate, ...]:
        if definition.operation is MappingOperation.CONSTANT:
            return (
                MappingCandidate(
                    value=definition.constant_value,
                    source_expression="constant",
                    source_column="configuration",
                ),
            )

        source_candidates = self._resolve_source_candidates(
            definition=definition,
            trace=trace,
            extracted_values=extracted_values,
        )

        if definition.operation is MappingOperation.COPY:
            return source_candidates

        if definition.operation is MappingOperation.REGEX:
            return self._apply_regex(
                definition=definition,
                candidates=source_candidates,
            )

        if definition.operation is MappingOperation.LOOKUP:
            return self._apply_lookup(
                definition=definition,
                candidates=source_candidates,
            )

        raise ValueError(
            f"Unsupported mapping operation: "
            f"{definition.operation.value}"
        )

    def _resolve_source_candidates(
        self,
        *,
        definition: MappingDefinition,
        trace: RawTrace,
        extracted_values: ExtractedTraceValues,
    ) -> tuple[MappingCandidate, ...]:
        source_type = definition.source_type

        if source_type is None:
            return ()

        if source_type is MappingSourceType.EXTRACTED_VALUE:
            return self._from_extracted_value(
                definition=definition,
                extracted_values=extracted_values,
            )

        if source_type is MappingSourceType.INFORMATION:
            return self._from_rows(
                rows=trace.rows,
                attribute_name="information",
            )

        if source_type is MappingSourceType.EVENT:
            return self._from_rows(
                rows=trace.rows,
                attribute_name="event",
            )

        if source_type is MappingSourceType.EVENT_TYPE:
            return self._from_rows(
                rows=trace.rows,
                attribute_name="event_type",
            )

        if source_type is MappingSourceType.RAW_FIELD:
            return self._from_raw_field(
                trace=trace,
                source_name=definition.source_name,
            )

        if source_type is MappingSourceType.TRACE_TEXT:
            return self._from_trace_text(
                trace
            )

        raise ValueError(
            f"Unsupported mapping source type: {source_type.value}"
        )

    @staticmethod
    def _from_extracted_value(
        *,
        definition: MappingDefinition,
        extracted_values: ExtractedTraceValues,
    ) -> tuple[MappingCandidate, ...]:
        if definition.source_name is None:
            return ()

        extracted_value = extracted_values.get_entry(
            definition.source_name
        )

        if extracted_value is None:
            return ()

        source_column = extracted_value.metadata.get(
            "source_column"
        )

        return (
            MappingCandidate(
                value=extracted_value.value,
                source_line_number=(
                    extracted_value.source_line_number
                ),
                source_expression=(
                    extracted_value.source_expression
                ),
                source_column=(
                    str(source_column)
                    if source_column is not None
                    else "extracted_value"
                ),
            ),
        )

    @staticmethod
    def _from_rows(
        *,
        rows: Iterable[RawTraceRow],
        attribute_name: str,
    ) -> tuple[MappingCandidate, ...]:
        candidates: list[MappingCandidate] = []

        for row in rows:
            value = getattr(
                row,
                attribute_name,
                None,
            )

            if value is None:
                continue

            if isinstance(value, str) and not value.strip():
                continue

            candidates.append(
                MappingCandidate(
                    value=value,
                    source_line_number=row.line_number,
                    source_expression=row.source_line,
                    source_column=attribute_name,
                )
            )

        return tuple(candidates)

    @staticmethod
    def _from_raw_field(
        *,
        trace: RawTrace,
        source_name: str | None,
    ) -> tuple[MappingCandidate, ...]:
        if source_name is None:
            return ()

        candidates: list[MappingCandidate] = []

        for row in trace.rows:
            value = row.raw_fields.get(
                source_name
            )

            if value is None:
                continue

            if isinstance(value, str) and not value.strip():
                continue

            candidates.append(
                MappingCandidate(
                    value=value,
                    source_line_number=row.line_number,
                    source_expression=row.source_line,
                    source_column=f"raw_fields.{source_name}",
                )
            )

        return tuple(candidates)

    @staticmethod
    def _from_trace_text(
        trace: RawTrace,
    ) -> tuple[MappingCandidate, ...]:
        candidates: list[MappingCandidate] = []

        for row in trace.rows:
            source_line = row.source_line

            if not source_line.strip():
                continue

            candidates.append(
                MappingCandidate(
                    value=source_line,
                    source_line_number=row.line_number,
                    source_expression=source_line,
                    source_column="trace_text",
                )
            )

        return tuple(candidates)

    @staticmethod
    def _apply_regex(
        *,
        definition: MappingDefinition,
        candidates: tuple[MappingCandidate, ...],
    ) -> tuple[MappingCandidate, ...]:
        pattern = definition.compile_pattern()

        if pattern is None:
            raise ValueError(
                "REGEX mapping does not contain a pattern"
            )

        results: list[MappingCandidate] = []

        for candidate in candidates:
            source_value = str(
                candidate.value
            )

            for match in pattern.finditer(
                source_value
            ):
                try:
                    matched_value = MappingEngine._extract_regex_group(
                        match=match,
                        group=definition.group,
                    )
                except (IndexError, KeyError) as exc:
                    raise ValueError(
                        f"Regex group {definition.group!r} does not "
                        f"exist for target "
                        f"'{definition.target_name}'"
                    ) from exc

                if matched_value is None:
                    continue

                results.append(
                    MappingCandidate(
                        value=matched_value,
                        source_line_number=(
                            candidate.source_line_number
                        ),
                        source_expression=match.group(0),
                        source_column=candidate.source_column,
                    )
                )

        return tuple(results)

    @staticmethod
    def _extract_regex_group(
        *,
        match: Any,
        group: str | int | None,
    ) -> str | None:
        if group is not None:
            return match.group(group)

        if match.lastindex:
            return match.group(1)

        return match.group(0)

    @staticmethod
    def _apply_lookup(
        *,
        definition: MappingDefinition,
        candidates: tuple[MappingCandidate, ...],
    ) -> tuple[MappingCandidate, ...]:
        lookup_values = definition.normalized_lookup_values()
        results: list[MappingCandidate] = []

        for candidate in candidates:
            lookup_key = definition.normalize_lookup_key(
                candidate.value
            )

            if lookup_key not in lookup_values:
                continue

            results.append(
                MappingCandidate(
                    value=lookup_values[lookup_key],
                    source_line_number=(
                        candidate.source_line_number
                    ),
                    source_expression=(
                        candidate.source_expression
                    ),
                    source_column=candidate.source_column,
                )
            )

        return tuple(results)

    @staticmethod
    def _select_candidate(
        *,
        definition: MappingDefinition,
        candidates: tuple[MappingCandidate, ...],
    ) -> tuple[MappingCandidate, str | None]:
        if len(candidates) == 1:
            return candidates[0], None

        strategy = definition.duplicate_strategy

        if strategy is MappingDuplicateStrategy.FIRST:
            return (
                candidates[0],
                (
                    f"Mapping produced {len(candidates)} candidates; "
                    "the first value was selected"
                ),
            )

        if strategy is MappingDuplicateStrategy.LAST:
            return (
                candidates[-1],
                (
                    f"Mapping produced {len(candidates)} candidates; "
                    "the last value was selected"
                ),
            )

        if strategy is MappingDuplicateStrategy.ERROR:
            raise ValueError(
                f"Mapping produced {len(candidates)} candidates while "
                "duplicate strategy is 'error'"
            )

        raise ValueError(
            f"Unsupported duplicate strategy: {strategy.value}"
        )

    @staticmethod
    def _handle_missing_value(
        definition: MappingDefinition,
    ) -> MappedValue:
        if definition.has_default:
            return MappedValue.defaulted(
                name=definition.target_name,
                value=definition.default_value,
                operation=definition.operation,
                value_type=definition.value_type,
                source_type=definition.source_type,
                source_name=definition.source_name,
                confidence=definition.confidence,
                reason=(
                    "No source value matched; configured default "
                    "value was used"
                ),
                metadata=definition.metadata,
            )

        warning = (
            "Required mapping did not produce a value"
            if definition.required
            else "Mapping did not produce a value"
        )

        return MappedValue.missing(
            name=definition.target_name,
            operation=definition.operation,
            value_type=definition.value_type,
            source_type=definition.source_type,
            source_name=definition.source_name,
            warning=warning,
            metadata=definition.metadata,
        )

    @classmethod
    def _convert_value(
        cls,
        *,
        value: Any,
        value_type: MappingValueType,
        strip_value: bool,
    ) -> Any:
        if value_type is MappingValueType.STRING:
            converted = str(
                value
            )

            return (
                converted.strip()
                if strip_value
                else converted
            )

        if value_type is MappingValueType.INTEGER:
            return cls._to_integer(
                value
            )

        if value_type is MappingValueType.FLOAT:
            return cls._to_float(
                value
            )

        if value_type is MappingValueType.BOOLEAN:
            return cls._to_boolean(
                value
            )

        if value_type is MappingValueType.DATETIME:
            return cls._to_datetime(
                value
            )

        raise ValueError(
            f"Unsupported mapping value type: {value_type.value}"
        )

    @staticmethod
    def _to_integer(
        value: Any,
    ) -> int:
        if isinstance(value, bool):
            raise ValueError(
                "Boolean value cannot be converted to integer"
            )

        if isinstance(value, int):
            return value

        if isinstance(value, float):
            if not value.is_integer():
                raise ValueError(
                    f"Non-integral float {value!r} cannot be "
                    "converted to integer"
                )

            return int(value)

        normalized = str(
            value
        ).strip()

        try:
            return int(
                normalized,
                10,
            )
        except ValueError as exc:
            raise ValueError(
                f"Cannot convert {value!r} to integer"
            ) from exc

    @staticmethod
    def _to_float(
        value: Any,
    ) -> float:
        if isinstance(value, bool):
            raise ValueError(
                "Boolean value cannot be converted to float"
            )

        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Cannot convert {value!r} to float"
            ) from exc

    @staticmethod
    def _to_boolean(
        value: Any,
    ) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, int) and value in {
            0,
            1,
        }:
            return bool(value)

        normalized = str(
            value
        ).strip().casefold()

        true_values = {
            "true",
            "yes",
            "y",
            "1",
            "on",
            "enabled",
        }
        false_values = {
            "false",
            "no",
            "n",
            "0",
            "off",
            "disabled",
        }

        if normalized in true_values:
            return True

        if normalized in false_values:
            return False

        raise ValueError(
            f"Cannot convert {value!r} to boolean"
        )

    @staticmethod
    def _to_datetime(
        value: Any,
    ) -> datetime:
        if isinstance(value, datetime):
            return value

        normalized = str(
            value
        ).strip()

        if normalized.endswith("Z"):
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
                f"Cannot convert {value!r} to ISO datetime"
            ) from exc
