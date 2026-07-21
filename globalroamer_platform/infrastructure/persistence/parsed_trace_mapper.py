from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from globalroamer_platform.domain.models.extracted_trace_values import (
    ExtractedTraceValues,
    ExtractedValue,
)
from globalroamer_platform.domain.models.mapped_trace_values import (
    MappedTraceValues,
    MappedValue,
    MappingValueStatus,
)
from globalroamer_platform.domain.models.mapping_definition import (
    MappingOperation,
    MappingSourceType,
    MappingValueType,
)
from globalroamer_platform.domain.models.operational_signal import (
    OperationalSignal,
    OperationalSignalType,
)
from globalroamer_platform.domain.models.parsed_evidence import (
    EvidenceSeverity,
    EvidenceType,
    ParsedEvidence,
)
from globalroamer_platform.domain.models.parsed_trace import (
    ParsedTrace,
)
from globalroamer_platform.domain.models.raw_trace import (
    RawTrace,
    RawTraceRow,
)
from globalroamer_platform.domain.models.source_artifact import (
    SourceArtifact,
    SourceArtifactType,
)


class ParsedTraceMapper:
    """
    Reconstruct a ParsedTrace aggregate from its persisted JSON snapshot.

    The expected snapshot format is the output produced by
    ``ParsedTrace.to_dict(include_raw_rows=True)``.

    Summary fields and other derived values are intentionally ignored.
    Domain models recompute those values from reconstructed state.
    """

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
    ) -> ParsedTrace:
        root = _require_mapping(
            data,
            field_name="parsed_trace",
        )

        raw_trace_data = _require_mapping_field(
            root,
            "raw_trace",
        )

        source_data = raw_trace_data.get("source")

        if source_data is None:
            source_data = root.get("source")

        if source_data is None:
            raise ValueError(
                "Parsed trace snapshot is missing source metadata"
            )

        source = cls._source_artifact(
            _require_mapping(
                source_data,
                field_name="source",
            )
        )

        raw_trace = cls._raw_trace(
            raw_trace_data,
            source=source,
        )

        extracted_values = cls._extracted_trace_values(
            _require_mapping_field(
                root,
                "extracted_values",
            )
        )

        mapped_values = cls._mapped_trace_values(
            _require_mapping_field(
                root,
                "mapped_values",
            )
        )

        evidences = tuple(
            cls._parsed_evidence(
                _require_mapping(
                    item,
                    field_name=f"evidences[{index}]",
                )
            )
            for index, item in enumerate(
                _require_list_field(
                    root,
                    "evidences",
                    default=[],
                )
            )
        )

        signals = tuple(
            cls._operational_signal(
                _require_mapping(
                    item,
                    field_name=f"signals[{index}]",
                )
            )
            for index, item in enumerate(
                _require_list_field(
                    root,
                    "signals",
                    default=[],
                )
            )
        )

        return ParsedTrace(
            raw_trace=raw_trace,
            extracted_values=extracted_values,
            mapped_values=mapped_values,
            evidences=evidences,
            signals=signals,
            warnings=_string_tuple(
                root.get("warnings", [])
            ),
            errors=_string_tuple(
                root.get("errors", [])
            ),
            metadata=dict(
                _optional_mapping(
                    root.get("metadata"),
                    field_name="metadata",
                )
            ),
        )

    @classmethod
    def _source_artifact(
        cls,
        data: Mapping[str, Any],
    ) -> SourceArtifact:
        return SourceArtifact(
            id=UUID(
                _require_string_field(
                    data,
                    "id",
                )
            ),
            artifact_type=SourceArtifactType(
                _require_string_field(
                    data,
                    "artifact_type",
                )
            ),
            source_path=Path(
                _require_string_field(
                    data,
                    "source_path",
                )
            ),
            filename=_require_string_field(
                data,
                "filename",
            ),
            extension=_require_string_field(
                data,
                "extension",
            ),
            size_bytes=_require_int_field(
                data,
                "size_bytes",
            ),
            checksum_sha256=_require_string_field(
                data,
                "checksum_sha256",
            ),
            loaded_at=_require_datetime_field(
                data,
                "loaded_at",
            ),
            content_type=_optional_string(
                data.get("content_type"),
                field_name="content_type",
            ),
            tenant_id=_optional_string(
                data.get("tenant_id"),
                field_name="tenant_id",
            ),
            trace_id=_optional_string(
                data.get("trace_id"),
                field_name="trace_id",
            ),
            testcase_id=_optional_string(
                data.get("testcase_id"),
                field_name="testcase_id",
            ),
        )

    @classmethod
    def _raw_trace(
        cls,
        data: Mapping[str, Any],
        *,
        source: SourceArtifact,
    ) -> RawTrace:
        rows_data = _require_list_field(
            data,
            "rows",
        )

        rows = tuple(
            cls._raw_trace_row(
                _require_mapping(
                    item,
                    field_name=f"raw_trace.rows[{index}]",
                )
            )
            for index, item in enumerate(rows_data)
        )

        return RawTrace(
            source=source,
            rows=rows,
            delimiter=_require_string_field(
                data,
                "delimiter",
            ),
            encoding=_require_string_field(
                data,
                "encoding",
            ),
            parser_warnings=_string_tuple(
                data.get("parser_warnings", [])
            ),
        )

    @staticmethod
    def _raw_trace_row(
        data: Mapping[str, Any],
    ) -> RawTraceRow:
        raw_fields = _optional_mapping(
            data.get("raw_fields"),
            field_name="raw_fields",
        )

        normalized_raw_fields: dict[str, str | None] = {}

        for key, value in raw_fields.items():
            if value is not None and not isinstance(
                value,
                str,
            ):
                raise TypeError(
                    "Raw trace field values must be strings or None: "
                    f"{key!r}"
                )

            normalized_raw_fields[str(key)] = value

        return RawTraceRow(
            line_number=_require_int_field(
                data,
                "line_number",
            ),
            timestamp=_optional_datetime(
                data.get("timestamp"),
                field_name="timestamp",
            ),
            call_id=_optional_string(
                data.get("call_id"),
                field_name="call_id",
            ),
            ptc=_optional_string(
                data.get("ptc"),
                field_name="ptc",
            ),
            event=_optional_string(
                data.get("event"),
                field_name="event",
            ),
            event_type=_optional_string(
                data.get("event_type"),
                field_name="event_type",
            ),
            information=_optional_string(
                data.get("information"),
                field_name="information",
            ),
            raw_fields=normalized_raw_fields,
        )

    @classmethod
    def _extracted_trace_values(
        cls,
        data: Mapping[str, Any],
    ) -> ExtractedTraceValues:
        values_data = _require_mapping_field(
            data,
            "values",
        )

        values: dict[str, ExtractedValue] = {}

        for name, item in values_data.items():
            item_data = _require_mapping(
                item,
                field_name=f"extracted_values.values[{name!r}]",
            )

            extracted_value = ExtractedValue(
                name=_require_string_field(
                    item_data,
                    "name",
                ),
                value=_require_present_field(
                    item_data,
                    "value",
                ),
                source_line_number=_optional_int(
                    item_data.get("source_line_number"),
                    field_name="source_line_number",
                ),
                source_expression=_optional_string(
                    item_data.get("source_expression"),
                    field_name="source_expression",
                ),
                extraction_method=_require_string_field(
                    item_data,
                    "extraction_method",
                ),
                confidence=_require_float_field(
                    item_data,
                    "confidence",
                ),
                metadata=dict(
                    _optional_mapping(
                        item_data.get("metadata"),
                        field_name="metadata",
                    )
                ),
            )

            if str(name) != extracted_value.name:
                raise ValueError(
                    "Extracted value dictionary key does not match "
                    f"the stored name: {name!r} != "
                    f"{extracted_value.name!r}"
                )

            values[extracted_value.name] = extracted_value

        return ExtractedTraceValues(
            values=values,
            extraction_warnings=_string_tuple(
                data.get("extraction_warnings", [])
            ),
        )

    @classmethod
    def _mapped_trace_values(
        cls,
        data: Mapping[str, Any],
    ) -> MappedTraceValues:
        values_data = _require_mapping_field(
            data,
            "values",
        )

        values: dict[str, MappedValue] = {}

        for name, item in values_data.items():
            item_data = _require_mapping(
                item,
                field_name=f"mapped_values.values[{name!r}]",
            )

            value_type = MappingValueType(
                _require_string_field(
                    item_data,
                    "value_type",
                )
            )

            mapped_value = MappedValue(
                name=_require_string_field(
                    item_data,
                    "name",
                ),
                value=cls._mapped_value(
                    item_data.get("value"),
                    value_type=value_type,
                ),
                status=MappingValueStatus(
                    _require_string_field(
                        item_data,
                        "status",
                    )
                ),
                operation=MappingOperation(
                    _require_string_field(
                        item_data,
                        "operation",
                    )
                ),
                value_type=value_type,
                source_type=_optional_enum(
                    item_data.get("source_type"),
                    enum_type=MappingSourceType,
                    field_name="source_type",
                ),
                source_name=_optional_string(
                    item_data.get("source_name"),
                    field_name="source_name",
                ),
                source_value=item_data.get("source_value"),
                source_line_number=_optional_int(
                    item_data.get("source_line_number"),
                    field_name="source_line_number",
                ),
                source_expression=_optional_string(
                    item_data.get("source_expression"),
                    field_name="source_expression",
                ),
                confidence=_require_float_field(
                    item_data,
                    "confidence",
                ),
                warning=_optional_string(
                    item_data.get("warning"),
                    field_name="warning",
                ),
                error=_optional_string(
                    item_data.get("error"),
                    field_name="error",
                ),
                metadata=dict(
                    _optional_mapping(
                        item_data.get("metadata"),
                        field_name="metadata",
                    )
                ),
            )

            if str(name) != mapped_value.name:
                raise ValueError(
                    "Mapped value dictionary key does not match "
                    f"the stored name: {name!r} != "
                    f"{mapped_value.name!r}"
                )

            values[mapped_value.name] = mapped_value

        return MappedTraceValues(
            values=values,
            mapping_warnings=_string_tuple(
                data.get("mapping_warnings", [])
            ),
            mapping_errors=_string_tuple(
                data.get("mapping_errors", [])
            ),
            configuration_version=_optional_string(
                data.get("configuration_version"),
                field_name="configuration_version",
            ),
        )

    @staticmethod
    def _mapped_value(
        value: Any,
        *,
        value_type: MappingValueType,
    ) -> Any:
        if value is None:
            return None

        if value_type is MappingValueType.DATETIME:
            if isinstance(value, datetime):
                return value

            if not isinstance(value, str):
                raise TypeError(
                    "Mapped datetime value must be an ISO-8601 string"
                )

            return _parse_datetime(
                value,
                field_name="mapped value",
            )

        return value

    @staticmethod
    def _parsed_evidence(
        data: Mapping[str, Any],
    ) -> ParsedEvidence:
        return ParsedEvidence(
            evidence_type=EvidenceType(
                _require_string_field(
                    data,
                    "evidence_type",
                )
            ),
            category=_require_string_field(
                data,
                "category",
            ),
            value=_require_string_field(
                data,
                "value",
            ),
            confidence=_require_float_field(
                data,
                "confidence",
            ),
            source_line_number=_require_int_field(
                data,
                "source_line_number",
            ),
            source_line=_require_string_field(
                data,
                "source_line",
            ),
            severity=EvidenceSeverity(
                _require_string_field(
                    data,
                    "severity",
                )
            ),
            timestamp=_optional_datetime(
                data.get("timestamp"),
                field_name="timestamp",
            ),
            protocol_layer=_optional_string(
                data.get("protocol_layer"),
                field_name="protocol_layer",
            ),
            event_code=_optional_string(
                data.get("event_code"),
                field_name="event_code",
            ),
            metric_name=_optional_string(
                data.get("metric_name"),
                field_name="metric_name",
            ),
            metadata=dict(
                _optional_mapping(
                    data.get("metadata"),
                    field_name="metadata",
                )
            ),
        )

    @staticmethod
    def _operational_signal(
        data: Mapping[str, Any],
    ) -> OperationalSignal:
        return OperationalSignal(
            signal_type=OperationalSignalType(
                _require_string_field(
                    data,
                    "signal_type",
                )
            ),
            source_line_number=_require_int_field(
                data,
                "source_line_number",
            ),
            source_line=_require_string_field(
                data,
                "source_line",
            ),
            matched_keyword=_require_string_field(
                data,
                "matched_keyword",
            ),
            confidence=_require_float_field(
                data,
                "confidence",
            ),
            timestamp=_optional_datetime(
                data.get("timestamp"),
                field_name="timestamp",
            ),
            metadata=dict(
                _optional_mapping(
                    data.get("metadata"),
                    field_name="metadata",
                )
            ),
        )


def _require_mapping(
    value: Any,
    *,
    field_name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(
            f"{field_name} must be a mapping"
        )

    return value


def _optional_mapping(
    value: Any,
    *,
    field_name: str,
) -> Mapping[str, Any]:
    if value is None:
        return {}

    return _require_mapping(
        value,
        field_name=field_name,
    )


def _require_mapping_field(
    data: Mapping[str, Any],
    field_name: str,
) -> Mapping[str, Any]:
    if field_name not in data:
        raise ValueError(
            f"Missing required field: {field_name}"
        )

    return _require_mapping(
        data[field_name],
        field_name=field_name,
    )


def _require_list_field(
    data: Mapping[str, Any],
    field_name: str,
    *,
    default: list[Any] | None = None,
) -> list[Any]:
    if field_name not in data:
        if default is not None:
            return default

        raise ValueError(
            f"Missing required field: {field_name}"
        )

    value = data[field_name]

    if not isinstance(value, list):
        raise TypeError(
            f"{field_name} must be a list"
        )

    return value


def _require_present_field(
    data: Mapping[str, Any],
    field_name: str,
) -> Any:
    if field_name not in data:
        raise ValueError(
            f"Missing required field: {field_name}"
        )

    value = data[field_name]

    if value is None:
        raise ValueError(
            f"{field_name} must not be None"
        )

    return value


def _require_string_field(
    data: Mapping[str, Any],
    field_name: str,
) -> str:
    if field_name not in data:
        raise ValueError(
            f"Missing required field: {field_name}"
        )

    value = data[field_name]

    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a string"
        )

    return value


def _optional_string(
    value: Any,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a string or None"
        )

    return value


def _require_int_field(
    data: Mapping[str, Any],
    field_name: str,
) -> int:
    if field_name not in data:
        raise ValueError(
            f"Missing required field: {field_name}"
        )

    return _as_int(
        data[field_name],
        field_name=field_name,
    )


def _optional_int(
    value: Any,
    *,
    field_name: str,
) -> int | None:
    if value is None:
        return None

    return _as_int(
        value,
        field_name=field_name,
    )


def _as_int(
    value: Any,
    *,
    field_name: str,
) -> int:
    if isinstance(value, bool) or not isinstance(
        value,
        int,
    ):
        raise TypeError(
            f"{field_name} must be an integer"
        )

    return value


def _require_float_field(
    data: Mapping[str, Any],
    field_name: str,
) -> float:
    if field_name not in data:
        raise ValueError(
            f"Missing required field: {field_name}"
        )

    value = data[field_name]

    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise TypeError(
            f"{field_name} must be a number"
        )

    return float(value)


def _require_datetime_field(
    data: Mapping[str, Any],
    field_name: str,
) -> datetime:
    if field_name not in data:
        raise ValueError(
            f"Missing required field: {field_name}"
        )

    value = _optional_datetime(
        data[field_name],
        field_name=field_name,
    )

    if value is None:
        raise ValueError(
            f"{field_name} must not be None"
        )

    return value


def _optional_datetime(
    value: Any,
    *,
    field_name: str,
) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be an ISO-8601 string or None"
        )

    return _parse_datetime(
        value,
        field_name=field_name,
    )


def _parse_datetime(
    value: str,
    *,
    field_name: str,
) -> datetime:
    normalized_value = value.strip()

    if normalized_value.endswith("Z"):
        normalized_value = (
            normalized_value[:-1] + "+00:00"
        )

    try:
        return datetime.fromisoformat(
            normalized_value
        )
    except ValueError as exc:
        raise ValueError(
            f"{field_name} contains an invalid ISO-8601 datetime: "
            f"{value!r}"
        ) from exc


def _string_tuple(
    value: Any,
) -> tuple[str, ...]:
    if value is None:
        return ()

    if not isinstance(value, (list, tuple)):
        raise TypeError(
            "Message collection must be a list or tuple"
        )

    result: list[str] = []

    for item in value:
        if not isinstance(item, str):
            raise TypeError(
                "Message collection must contain strings"
            )

        result.append(item)

    return tuple(result)


def _optional_enum(
    value: Any,
    *,
    enum_type: type,
    field_name: str,
) -> Any:
    if value is None:
        return None

    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a string or None"
        )

    return enum_type(value)
