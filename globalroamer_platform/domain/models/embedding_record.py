"""Domain model representing an embedding generated for a trace chunk."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class EmbeddingRecord:
    """
    Vector embedding generated from one persisted trace chunk.

    The record keeps the embedding result provider-neutral. Provider-specific
    clients belong to the infrastructure layer, while the domain stores only
    the model identity and generated vector.

    An embedding is uniquely associated with:

    - tenant
    - trace
    - trace chunk
    - embedding model
    - embedding model version
    """

    id: UUID
    tenant_id: str
    trace_id: str
    testcase_id: str | None
    chunk_id: UUID

    model_name: str
    model_version: str

    dimensions: int
    embedding: tuple[float, ...]

    content_checksum: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        trace_id: str,
        testcase_id: str | None,
        chunk_id: UUID,
        model_name: str,
        model_version: str,
        embedding: Sequence[float],
        content_checksum: str,
        record_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> EmbeddingRecord:
        """Create and validate an embedding record."""

        normalized_tenant_id = cls._require_non_empty_string(
            tenant_id,
            field_name="tenant_id",
        )
        normalized_trace_id = cls._require_non_empty_string(
            trace_id,
            field_name="trace_id",
        )
        normalized_testcase_id = cls._normalize_optional_string(
            testcase_id,
            field_name="testcase_id",
        )

        if not isinstance(chunk_id, UUID):
            raise TypeError("chunk_id must be a UUID")

        normalized_model_name = cls._require_non_empty_string(
            model_name,
            field_name="model_name",
        )
        normalized_model_version = cls._require_non_empty_string(
            model_version,
            field_name="model_version",
        )

        normalized_embedding = cls._normalize_embedding(
            embedding,
        )

        normalized_checksum = cls._normalize_checksum(
            content_checksum,
        )

        normalized_record_id = (
            uuid4()
            if record_id is None
            else record_id
        )

        if not isinstance(normalized_record_id, UUID):
            raise TypeError("record_id must be a UUID")

        normalized_created_at = cls._normalize_datetime(
            datetime.now(timezone.utc)
            if created_at is None
            else created_at,
        )

        return cls(
            id=normalized_record_id,
            tenant_id=normalized_tenant_id,
            trace_id=normalized_trace_id,
            testcase_id=normalized_testcase_id,
            chunk_id=chunk_id,
            model_name=normalized_model_name,
            model_version=normalized_model_version,
            dimensions=len(normalized_embedding),
            embedding=normalized_embedding,
            content_checksum=normalized_checksum,
            created_at=normalized_created_at,
        )

    def belongs_to(
        self,
        *,
        tenant_id: str,
        trace_id: str,
    ) -> bool:
        """Return whether this record belongs to the supplied tenant trace."""

        return (
            self.tenant_id == tenant_id
            and self.trace_id == trace_id
        )

    def uses_model(
        self,
        *,
        model_name: str,
        model_version: str,
    ) -> bool:
        """Return whether this record was produced by the supplied model."""

        return (
            self.model_name == model_name
            and self.model_version == model_version
        )

    @property
    def model_identity(self) -> tuple[str, str]:
        """Return the stable model name and version identity."""

        return (
            self.model_name,
            self.model_version,
        )

    @staticmethod
    def _require_non_empty_string(
        value: object,
        *,
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

    @classmethod
    def _normalize_optional_string(
        cls,
        value: object,
        *,
        field_name: str,
    ) -> str | None:
        if value is None:
            return None

        return cls._require_non_empty_string(
            value,
            field_name=field_name,
        )

    @staticmethod
    def _normalize_embedding(
        embedding: Sequence[float],
    ) -> tuple[float, ...]:
        if isinstance(
            embedding,
            (
                str,
                bytes,
                bytearray,
            ),
        ):
            raise TypeError(
                "embedding must be a sequence of numbers"
            )

        if not isinstance(embedding, Sequence):
            raise TypeError(
                "embedding must be a sequence of numbers"
            )

        if not embedding:
            raise ValueError(
                "embedding must not be empty"
            )

        normalized_values: list[float] = []

        for index, value in enumerate(embedding):
            if isinstance(value, bool) or not isinstance(
                value,
                (
                    int,
                    float,
                ),
            ):
                raise TypeError(
                    "embedding values must be numeric: "
                    f"invalid value at index {index}"
                )

            normalized_value = float(value)

            if not math.isfinite(normalized_value):
                raise ValueError(
                    "embedding values must be finite: "
                    f"invalid value at index {index}"
                )

            normalized_values.append(
                normalized_value,
            )

        return tuple(normalized_values)

    @staticmethod
    def _normalize_checksum(
        value: object,
    ) -> str:
        if not isinstance(value, str):
            raise TypeError(
                "content_checksum must be a string"
            )

        normalized = value.strip().lower()

        if not normalized:
            raise ValueError(
                "content_checksum must not be empty"
            )

        if len(normalized) != 64:
            raise ValueError(
                "content_checksum must be a SHA-256 "
                "hexadecimal digest"
            )

        try:
            int(normalized, 16)
        except ValueError as exc:
            raise ValueError(
                "content_checksum must be a SHA-256 "
                "hexadecimal digest"
            ) from exc

        return normalized

    @staticmethod
    def _normalize_datetime(
        value: object,
    ) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError(
                "created_at must be a datetime"
            )

        if value.tzinfo is None:
            raise ValueError(
                "created_at must be timezone-aware"
            )

        return value.astimezone(timezone.utc)
