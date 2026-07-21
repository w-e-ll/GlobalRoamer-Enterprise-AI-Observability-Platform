from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class TraceChunk:
    """
    Immutable domain representation of a chunk created from normalized
    operational events.

    A TraceChunk is the unit that will later be embedded, indexed in a
    vector store, and used for semantic search and AI analysis.
    """

    id: UUID
    tenant_id: str
    trace_id: str
    testcase_id: str | None
    chunk_index: int
    text: str
    content_hash: str
    event_ids: tuple[UUID, ...]
    event_count: int
    event_names: tuple[str, ...]
    event_families: tuple[str, ...]
    severities: tuple[str, ...]
    causes: tuple[str, ...]
    tags: tuple[str, ...]
    has_failure: bool
    has_high_severity: bool
    has_retry_recommended: bool
    created_at: datetime

    def __post_init__(self) -> None:
        self._validate_uuid(
            value=self.id,
            field_name="id",
        )
        self._validate_required_text(
            value=self.tenant_id,
            field_name="tenant_id",
        )
        self._validate_required_text(
            value=self.trace_id,
            field_name="trace_id",
        )
        self._validate_optional_text(
            value=self.testcase_id,
            field_name="testcase_id",
        )
        self._validate_chunk_index()
        self._validate_required_text(
            value=self.text,
            field_name="text",
        )
        self._validate_content_hash()
        self._validate_event_ids()
        self._validate_event_count()
        self._validate_string_tuple(
            value=self.event_names,
            field_name="event_names",
        )
        self._validate_string_tuple(
            value=self.event_families,
            field_name="event_families",
        )
        self._validate_string_tuple(
            value=self.severities,
            field_name="severities",
        )
        self._validate_string_tuple(
            value=self.causes,
            field_name="causes",
        )
        self._validate_string_tuple(
            value=self.tags,
            field_name="tags",
        )
        self._validate_boolean(
            value=self.has_failure,
            field_name="has_failure",
        )
        self._validate_boolean(
            value=self.has_high_severity,
            field_name="has_high_severity",
        )
        self._validate_boolean(
            value=self.has_retry_recommended,
            field_name="has_retry_recommended",
        )
        self._validate_created_at()

        expected_hash = self.calculate_content_hash(
            self.text
        )

        if self.content_hash != expected_hash:
            raise ValueError(
                "content_hash does not match the SHA-256 hash "
                "of text"
            )

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        trace_id: str,
        testcase_id: str | None,
        chunk_index: int,
        text: str,
        event_ids: tuple[UUID, ...],
        event_names: tuple[str, ...] = (),
        event_families: tuple[str, ...] = (),
        severities: tuple[str, ...] = (),
        causes: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
        has_failure: bool = False,
        has_high_severity: bool = False,
        has_retry_recommended: bool = False,
        chunk_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> TraceChunk:
        """
        Create a validated TraceChunk.

        The content hash is calculated from the exact chunk text. This
        allows later embedding and indexing stages to detect unchanged
        content and avoid unnecessary recomputation.
        """
        normalized_text = cls._normalize_required_text(
            value=text,
            field_name="text",
        )

        normalized_event_ids = cls._normalize_event_ids(
            event_ids
        )

        return cls(
            id=chunk_id or uuid4(),
            tenant_id=cls._normalize_required_text(
                value=tenant_id,
                field_name="tenant_id",
            ),
            trace_id=cls._normalize_required_text(
                value=trace_id,
                field_name="trace_id",
            ),
            testcase_id=cls._normalize_optional_text(
                testcase_id
            ),
            chunk_index=chunk_index,
            text=normalized_text,
            content_hash=cls.calculate_content_hash(
                normalized_text
            ),
            event_ids=normalized_event_ids,
            event_count=len(normalized_event_ids),
            event_names=cls._normalize_string_tuple(
                event_names
            ),
            event_families=cls._normalize_string_tuple(
                event_families
            ),
            severities=cls._normalize_string_tuple(
                severities
            ),
            causes=cls._normalize_string_tuple(
                causes
            ),
            tags=cls._normalize_string_tuple(
                tags
            ),
            has_failure=has_failure,
            has_high_severity=has_high_severity,
            has_retry_recommended=(
                has_retry_recommended
            ),
            created_at=created_at or datetime.now(
                timezone.utc
            ),
        )

    @staticmethod
    def calculate_content_hash(text: str) -> str:
        """
        Calculate a deterministic SHA-256 hash for chunk content.
        """
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        return hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()

    @property
    def deterministic_key(self) -> str:
        """
        Return a stable logical key inside a tenant and trace.

        The UUID remains the database identity. This key identifies the
        logical chunk position and can later be used for idempotency.
        """
        return (
            f"{self.tenant_id}:"
            f"{self.trace_id}:"
            f"{self.chunk_index}"
        )

    @property
    def character_count(self) -> int:
        return len(self.text)

    @property
    def is_empty(self) -> bool:
        return not bool(self.text.strip())

    @staticmethod
    def _normalize_required_text(
        *,
        value: str,
        field_name: str,
    ) -> str:
        if not isinstance(value, str):
            raise TypeError(
                f"{field_name} must be a string"
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                f"{field_name} must not be empty"
            )

        return normalized

    @staticmethod
    def _normalize_optional_text(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        if not isinstance(value, str):
            raise TypeError(
                "testcase_id must be a string or None"
            )

        normalized = value.strip()

        return normalized or None

    @staticmethod
    def _normalize_event_ids(
        event_ids: tuple[UUID, ...],
    ) -> tuple[UUID, ...]:
        if not isinstance(event_ids, tuple):
            raise TypeError(
                "event_ids must be a tuple"
            )

        if not event_ids:
            raise ValueError(
                "event_ids must contain at least one event"
            )

        normalized: list[UUID] = []
        seen: set[UUID] = set()

        for event_id in event_ids:
            if not isinstance(event_id, UUID):
                raise TypeError(
                    "every event_ids item must be a UUID"
                )

            if event_id in seen:
                continue

            seen.add(event_id)
            normalized.append(event_id)

        return tuple(normalized)

    @staticmethod
    def _normalize_string_tuple(
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if not isinstance(values, tuple):
            raise TypeError(
                "metadata collections must be tuples"
            )

        normalized: set[str] = set()

        for value in values:
            if not isinstance(value, str):
                raise TypeError(
                    "metadata collection items must "
                    "be strings"
                )

            stripped = value.strip()

            if stripped:
                normalized.add(stripped)

        return tuple(sorted(normalized))

    @staticmethod
    def _validate_uuid(
        *,
        value: UUID,
        field_name: str,
    ) -> None:
        if not isinstance(value, UUID):
            raise TypeError(
                f"{field_name} must be a UUID"
            )

    @staticmethod
    def _validate_required_text(
        *,
        value: str,
        field_name: str,
    ) -> None:
        if not isinstance(value, str):
            raise TypeError(
                f"{field_name} must be a string"
            )

        if not value.strip():
            raise ValueError(
                f"{field_name} must not be empty"
            )

        if value != value.strip():
            raise ValueError(
                f"{field_name} must be normalized"
            )

    @staticmethod
    def _validate_optional_text(
        *,
        value: str | None,
        field_name: str,
    ) -> None:
        if value is None:
            return

        if not isinstance(value, str):
            raise TypeError(
                f"{field_name} must be a string or None"
            )

        if not value.strip():
            raise ValueError(
                f"{field_name} must not be empty"
            )

        if value != value.strip():
            raise ValueError(
                f"{field_name} must be normalized"
            )

    def _validate_chunk_index(self) -> None:
        if (
            not isinstance(self.chunk_index, int)
            or isinstance(self.chunk_index, bool)
        ):
            raise TypeError(
                "chunk_index must be an integer"
            )

        if self.chunk_index < 0:
            raise ValueError(
                "chunk_index must be greater than or "
                "equal to zero"
            )

    def _validate_content_hash(self) -> None:
        if not isinstance(self.content_hash, str):
            raise TypeError(
                "content_hash must be a string"
            )

        if len(self.content_hash) != 64:
            raise ValueError(
                "content_hash must be a 64-character "
                "SHA-256 hexadecimal digest"
            )

        try:
            int(self.content_hash, 16)
        except ValueError as exc:
            raise ValueError(
                "content_hash must be hexadecimal"
            ) from exc

    def _validate_event_ids(self) -> None:
        if not isinstance(self.event_ids, tuple):
            raise TypeError(
                "event_ids must be a tuple"
            )

        if not self.event_ids:
            raise ValueError(
                "event_ids must contain at least one event"
            )

        for event_id in self.event_ids:
            if not isinstance(event_id, UUID):
                raise TypeError(
                    "every event_ids item must be a UUID"
                )

        if len(set(self.event_ids)) != len(
            self.event_ids
        ):
            raise ValueError(
                "event_ids must not contain duplicates"
            )

    def _validate_event_count(self) -> None:
        if (
            not isinstance(self.event_count, int)
            or isinstance(self.event_count, bool)
        ):
            raise TypeError(
                "event_count must be an integer"
            )

        if self.event_count <= 0:
            raise ValueError(
                "event_count must be greater than zero"
            )

        if self.event_count != len(self.event_ids):
            raise ValueError(
                "event_count must equal the number of "
                "event_ids"
            )

    @staticmethod
    def _validate_string_tuple(
        *,
        value: tuple[str, ...],
        field_name: str,
    ) -> None:
        if not isinstance(value, tuple):
            raise TypeError(
                f"{field_name} must be a tuple"
            )

        for item in value:
            if not isinstance(item, str):
                raise TypeError(
                    f"every {field_name} item must "
                    "be a string"
                )

            if not item.strip():
                raise ValueError(
                    f"{field_name} must not contain "
                    "empty values"
                )

            if item != item.strip():
                raise ValueError(
                    f"{field_name} items must be normalized"
                )

        expected = tuple(sorted(set(value)))

        if value != expected:
            raise ValueError(
                f"{field_name} must be unique and sorted"
            )

    @staticmethod
    def _validate_boolean(
        *,
        value: bool,
        field_name: str,
    ) -> None:
        if not isinstance(value, bool):
            raise TypeError(
                f"{field_name} must be a boolean"
            )

    def _validate_created_at(self) -> None:
        if not isinstance(self.created_at, datetime):
            raise TypeError(
                "created_at must be a datetime"
            )

        if (
            self.created_at.tzinfo is None
            or self.created_at.utcoffset() is None
        ):
            raise ValueError(
                "created_at must be timezone-aware"
            )
