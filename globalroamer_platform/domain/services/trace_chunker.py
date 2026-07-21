from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from globalroamer_platform.domain.models.operational_event import (
    OperationalEvent,
)
from globalroamer_platform.domain.models.trace_chunk import (
    TraceChunk,
)


@dataclass(frozen=True, slots=True)
class TraceChunker:
    """
    Pure domain service that converts normalized OperationalEvent objects
    into immutable TraceChunk objects.

    The service:

    - performs no database access;
    - performs no logging;
    - creates no outbox events;
    - does not commit transactions;
    - produces deterministic chunks for the same input and configuration.

    Chunk limits are measured in characters. Events are never split across
    chunks. Therefore, one unusually large event may produce a chunk larger
    than chunk_size.
    """

    chunk_size: int = 4000
    chunk_overlap: int = 400

    def __post_init__(self) -> None:
        if (
            not isinstance(self.chunk_size, int)
            or isinstance(self.chunk_size, bool)
        ):
            raise TypeError(
                "chunk_size must be an integer"
            )

        if self.chunk_size <= 0:
            raise ValueError(
                "chunk_size must be greater than zero"
            )

        if (
            not isinstance(self.chunk_overlap, int)
            or isinstance(self.chunk_overlap, bool)
        ):
            raise TypeError(
                "chunk_overlap must be an integer"
            )

        if self.chunk_overlap < 0:
            raise ValueError(
                "chunk_overlap must be greater than or "
                "equal to zero"
            )

        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                "chunk_overlap must be smaller than "
                "chunk_size"
            )

    def chunk(
        self,
        operational_events: tuple[
            OperationalEvent,
            ...,
        ],
    ) -> tuple[TraceChunk, ...]:
        """
        Convert ordered OperationalEvent objects into TraceChunk objects.

        Empty input produces no chunks.
        """
        self._validate_events_collection(
            operational_events
        )

        if not operational_events:
            return ()

        ordered_events = self._order_events(
            operational_events
        )

        self._validate_trace_consistency(
            ordered_events
        )

        tenant_id = self._required_string_attribute(
            ordered_events[0],
            "tenant_id",
        )
        trace_id = self._required_string_attribute(
            ordered_events[0],
            "trace_id",
        )
        testcase_id = self._optional_string_attribute(
            ordered_events[0],
            "testcase_id",
        )

        chunks: list[TraceChunk] = []
        current_events: list[OperationalEvent] = []
        current_lines: list[str] = []
        current_size = 0
        chunk_index = 0

        for event in ordered_events:
            event_text = self.event_to_text(event)
            event_size = len(event_text)

            separator_size = (
                1 if current_lines else 0
            )

            exceeds_limit = (
                current_events
                and (
                    current_size
                    + separator_size
                    + event_size
                    > self.chunk_size
                )
            )

            if exceeds_limit:
                chunks.append(
                    self._build_chunk(
                        tenant_id=tenant_id,
                        trace_id=trace_id,
                        testcase_id=testcase_id,
                        chunk_index=chunk_index,
                        events=tuple(current_events),
                        lines=tuple(current_lines),
                    )
                )

                chunk_index += 1

                overlap_events = (
                    self._select_overlap_events(
                        events=tuple(current_events),
                        lines=tuple(current_lines),
                    )
                )

                current_events = list(
                    overlap_events
                )
                current_lines = [
                    self.event_to_text(
                        overlap_event
                    )
                    for overlap_event in overlap_events
                ]
                current_size = self._text_size(
                    current_lines
                )

            current_events.append(event)
            current_lines.append(event_text)
            current_size = self._text_size(
                current_lines
            )

        if current_events:
            chunks.append(
                self._build_chunk(
                    tenant_id=tenant_id,
                    trace_id=trace_id,
                    testcase_id=testcase_id,
                    chunk_index=chunk_index,
                    events=tuple(current_events),
                    lines=tuple(current_lines),
                )
            )

        return tuple(chunks)

    def event_to_text(
        self,
        event: OperationalEvent,
    ) -> str:
        """
        Convert one OperationalEvent into deterministic embedding text.

        Empty attributes are omitted so that the final text remains compact.
        """
        fields: tuple[
            tuple[str, Any],
            ...,
        ] = (
            (
                "event_id",
                self._attribute(
                    event,
                    "id",
                    fallback_names=("event_id",),
                ),
            ),
            (
                "sequence_number",
                self._attribute(
                    event,
                    "sequence_number",
                ),
            ),
            (
                "testcase_id",
                self._attribute(
                    event,
                    "testcase_id",
                ),
            ),
            (
                "timestamp",
                self._attribute(
                    event,
                    "timestamp",
                    fallback_names=(
                        "occurred_at",
                        "event_timestamp",
                    ),
                ),
            ),
            (
                "event_family",
                self._attribute(
                    event,
                    "event_family",
                ),
            ),
            (
                "protocol_layer",
                self._attribute(
                    event,
                    "protocol_layer",
                ),
            ),
            (
                "event_name",
                self._attribute(
                    event,
                    "event_name",
                    fallback_names=("name",),
                ),
            ),
            (
                "severity",
                self._attribute(
                    event,
                    "severity",
                ),
            ),
            (
                "result",
                self._attribute(
                    event,
                    "result",
                ),
            ),
            (
                "operator",
                self._attribute(
                    event,
                    "operator",
                ),
            ),
            (
                "country",
                self._attribute(
                    event,
                    "country",
                ),
            ),
            (
                "network_domain",
                self._attribute(
                    event,
                    "network_domain",
                ),
            ),
            (
                "workflow_stage",
                self._attribute(
                    event,
                    "workflow_stage",
                ),
            ),
            (
                "direction",
                self._attribute(
                    event,
                    "direction",
                ),
            ),
            (
                "cause",
                self._attribute(
                    event,
                    "cause",
                ),
            ),
            (
                "retry_recommended",
                self._attribute(
                    event,
                    "retry_recommended",
                ),
            ),
            (
                "recommendation",
                self._attribute(
                    event,
                    "recommendation",
                ),
            ),
            (
                "message",
                self._attribute(
                    event,
                    "normalized_message",
                    fallback_names=("message",),
                ),
            ),
            (
                "tags",
                self._attribute(
                    event,
                    "tags",
                ),
            ),
            (
                "metadata",
                self._attribute(
                    event,
                    "metadata",
                ),
            ),
            (
                "extracted_values",
                self._attribute(
                    event,
                    "extracted_values",
                ),
            ),
            (
                "raw_message",
                self._attribute(
                    event,
                    "raw_message",
                    fallback_names=("raw",),
                ),
            ),
        )

        parts: list[str] = []

        for field_name, value in fields:
            normalized_value = (
                self._value_to_text(value)
            )

            if normalized_value is None:
                continue

            parts.append(
                f"{field_name}={normalized_value}"
            )

        if not parts:
            event_id = self._event_id(event)

            return f"event_id={event_id}"

        return " | ".join(parts)

    def _build_chunk(
        self,
        *,
        tenant_id: str,
        trace_id: str,
        testcase_id: str | None,
        chunk_index: int,
        events: tuple[OperationalEvent, ...],
        lines: tuple[str, ...],
    ) -> TraceChunk:
        if not events:
            raise ValueError(
                "a chunk must contain at least one event"
            )

        if len(events) != len(lines):
            raise ValueError(
                "events and lines must have equal length"
            )

        event_ids = tuple(
            self._event_id(event)
            for event in events
        )

        event_names = self._collect_strings(
            events,
            attribute_name="event_name",
            fallback_names=("name",),
        )
        event_families = self._collect_strings(
            events,
            attribute_name="event_family",
        )
        severities = self._collect_strings(
            events,
            attribute_name="severity",
        )
        causes = self._collect_strings(
            events,
            attribute_name="cause",
        )
        tags = self._collect_tags(events)

        has_failure = any(
            self._is_failure(event)
            for event in events
        )
        has_high_severity = any(
            self._is_high_severity(event)
            for event in events
        )
        has_retry_recommended = any(
            bool(
                self._attribute(
                    event,
                    "retry_recommended",
                )
            )
            for event in events
        )

        return TraceChunk.create(
            tenant_id=tenant_id,
            trace_id=trace_id,
            testcase_id=testcase_id,
            chunk_index=chunk_index,
            text="\n".join(lines),
            event_ids=event_ids,
            event_names=event_names,
            event_families=event_families,
            severities=severities,
            causes=causes,
            tags=tags,
            has_failure=has_failure,
            has_high_severity=has_high_severity,
            has_retry_recommended=(
                has_retry_recommended
            ),
        )

    def _select_overlap_events(
        self,
        *,
        events: tuple[OperationalEvent, ...],
        lines: tuple[str, ...],
    ) -> tuple[OperationalEvent, ...]:
        """
        Select complete events from the end of the previous chunk.

        Events are not split. The resulting overlap can therefore be slightly
        larger than chunk_overlap.
        """
        if self.chunk_overlap == 0:
            return ()

        if len(events) != len(lines):
            raise ValueError(
                "events and lines must have equal length"
            )

        selected: list[OperationalEvent] = []
        selected_size = 0

        for event, line in reversed(
            tuple(zip(events, lines, strict=True))
        ):
            selected.insert(0, event)
            selected_size += len(line)

            if len(selected) > 1:
                selected_size += 1

            if selected_size >= self.chunk_overlap:
                break

        return tuple(selected)

    @staticmethod
    def _text_size(lines: Iterable[str]) -> int:
        return len("\n".join(lines))

    @staticmethod
    def _validate_events_collection(
        operational_events: tuple[
            OperationalEvent,
            ...,
        ],
    ) -> None:
        if not isinstance(
            operational_events,
            tuple,
        ):
            raise TypeError(
                "operational_events must be a tuple"
            )

        for event in operational_events:
            if not isinstance(
                event,
                OperationalEvent,
            ):
                raise TypeError(
                    "every operational_events item must "
                    "be an OperationalEvent"
                )

    def _validate_trace_consistency(
        self,
        events: tuple[OperationalEvent, ...],
    ) -> None:
        first_event = events[0]

        expected_tenant_id = (
            self._required_string_attribute(
                first_event,
                "tenant_id",
            )
        )
        expected_trace_id = (
            self._required_string_attribute(
                first_event,
                "trace_id",
            )
        )
        expected_testcase_id = (
            self._optional_string_attribute(
                first_event,
                "testcase_id",
            )
        )

        seen_event_ids: set[UUID] = set()

        for event in events:
            tenant_id = (
                self._required_string_attribute(
                    event,
                    "tenant_id",
                )
            )
            trace_id = (
                self._required_string_attribute(
                    event,
                    "trace_id",
                )
            )
            testcase_id = (
                self._optional_string_attribute(
                    event,
                    "testcase_id",
                )
            )
            event_id = self._event_id(event)

            if tenant_id != expected_tenant_id:
                raise ValueError(
                    "all operational events must have "
                    "the same tenant_id"
                )

            if trace_id != expected_trace_id:
                raise ValueError(
                    "all operational events must have "
                    "the same trace_id"
                )

            if testcase_id != expected_testcase_id:
                raise ValueError(
                    "all operational events must have "
                    "the same testcase_id"
                )

            if event_id in seen_event_ids:
                raise ValueError(
                    "operational events must have "
                    "unique IDs"
                )

            seen_event_ids.add(event_id)

    def _order_events(
        self,
        events: tuple[OperationalEvent, ...],
    ) -> tuple[OperationalEvent, ...]:
        return tuple(
            sorted(
                events,
                key=self._event_sort_key,
            )
        )

    def _event_sort_key(
        self,
        event: OperationalEvent,
    ) -> tuple[int, str, str]:
        sequence_number = self._attribute(
            event,
            "sequence_number",
        )

        if (
            not isinstance(sequence_number, int)
            or isinstance(sequence_number, bool)
        ):
            sequence_number = 0

        timestamp = self._attribute(
            event,
            "timestamp",
            fallback_names=(
                "occurred_at",
                "event_timestamp",
            ),
        )

        timestamp_text = (
            timestamp.isoformat()
            if isinstance(timestamp, datetime)
            else str(timestamp or "")
        )

        return (
            sequence_number,
            timestamp_text,
            str(self._event_id(event)),
        )

    def _event_id(
        self,
        event: OperationalEvent,
    ) -> UUID:
        event_id = self._attribute(
            event,
            "id",
            fallback_names=("event_id",),
        )

        if not isinstance(event_id, UUID):
            raise TypeError(
                "OperationalEvent id must be a UUID"
            )

        return event_id

    def _is_failure(
        self,
        event: OperationalEvent,
    ) -> bool:
        result = self._normalized_scalar(
            self._attribute(
                event,
                "result",
            )
        )

        severity = self._normalized_scalar(
            self._attribute(
                event,
                "severity",
            )
        )

        return result in {
            "failed",
            "failure",
            "error",
            "timeout",
        } or severity in {
            "error",
            "critical",
            "fatal",
        }

    def _is_high_severity(
        self,
        event: OperationalEvent,
    ) -> bool:
        severity = self._normalized_scalar(
            self._attribute(
                event,
                "severity",
            )
        )

        return severity in {
            "high",
            "critical",
            "fatal",
            "error",
        }

    def _collect_strings(
        self,
        events: tuple[OperationalEvent, ...],
        *,
        attribute_name: str,
        fallback_names: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        values: set[str] = set()

        for event in events:
            value = self._attribute(
                event,
                attribute_name,
                fallback_names=fallback_names,
            )

            normalized = self._scalar_to_string(
                value
            )

            if normalized:
                values.add(normalized)

        return tuple(sorted(values))

    def _collect_tags(
        self,
        events: tuple[OperationalEvent, ...],
    ) -> tuple[str, ...]:
        tags: set[str] = set()

        for event in events:
            raw_tags = self._attribute(
                event,
                "tags",
            )

            if raw_tags is None:
                continue

            if isinstance(raw_tags, str):
                raw_values: Iterable[Any] = (
                    raw_tags,
                )
            elif isinstance(
                raw_tags,
                (tuple, list, set, frozenset),
            ):
                raw_values = raw_tags
            else:
                raise TypeError(
                    "OperationalEvent tags must be "
                    "a collection of strings"
                )

            for raw_tag in raw_values:
                normalized = (
                    self._scalar_to_string(
                        raw_tag
                    )
                )

                if normalized:
                    tags.add(normalized)

        return tuple(sorted(tags))

    @staticmethod
    def _attribute(
        event: OperationalEvent,
        name: str,
        *,
        fallback_names: tuple[str, ...] = (),
    ) -> Any:
        if hasattr(event, name):
            return getattr(event, name)

        for fallback_name in fallback_names:
            if hasattr(event, fallback_name):
                return getattr(
                    event,
                    fallback_name,
                )

        return None

    def _required_string_attribute(
        self,
        event: OperationalEvent,
        name: str,
    ) -> str:
        value = self._attribute(
            event,
            name,
        )

        if not isinstance(value, str):
            raise TypeError(
                f"OperationalEvent {name} must be "
                "a string"
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                f"OperationalEvent {name} must not "
                "be empty"
            )

        return normalized

    def _optional_string_attribute(
        self,
        event: OperationalEvent,
        name: str,
    ) -> str | None:
        value = self._attribute(
            event,
            name,
        )

        if value is None:
            return None

        if not isinstance(value, str):
            raise TypeError(
                f"OperationalEvent {name} must be "
                "a string or None"
            )

        normalized = value.strip()

        return normalized or None

    @classmethod
    def _value_to_text(
        cls,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(value, Enum):
            return cls._value_to_text(
                value.value
            )

        if isinstance(value, bool):
            return (
                "true"
                if value
                else "false"
            )

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, UUID):
            return str(value)

        if isinstance(value, dict):
            items: list[str] = []

            for key in sorted(
                value,
                key=lambda item: str(item),
            ):
                nested_value = value[key]
                nested_text = cls._value_to_text(
                    nested_value
                )

                if nested_text is None:
                    continue

                items.append(
                    f"{key}={nested_text}"
                )

            if not items:
                return None

            return "{" + ", ".join(items) + "}"

        if isinstance(
            value,
            (tuple, list, set, frozenset),
        ):
            normalized_items = [
                item_text
                for item in value
                if (
                    item_text
                    := cls._value_to_text(item)
                )
                is not None
            ]

            if not normalized_items:
                return None

            if isinstance(
                value,
                (set, frozenset),
            ):
                normalized_items.sort()

            return (
                "["
                + ", ".join(normalized_items)
                + "]"
            )

        text = str(value).strip()

        return text or None

    @classmethod
    def _scalar_to_string(
        cls,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(value, Enum):
            value = value.value

        if isinstance(
            value,
            (dict, list, tuple, set, frozenset),
        ):
            return None

        normalized = str(value).strip()

        return normalized or None

    @classmethod
    def _normalized_scalar(
        cls,
        value: Any,
    ) -> str:
        normalized = cls._scalar_to_string(
            value
        )

        return (
            normalized.casefold()
            if normalized
            else ""
        )
