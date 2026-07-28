"""Domain entity representing a trace source artifact."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID


class ArtifactStorageType(str, Enum):
    """Supported artifact storage backends."""

    FILESYSTEM = "filesystem"
    OBJECT_STORAGE = "object_storage"


class ArtifactStatus(str, Enum):
    """Artifact lifecycle state."""

    AVAILABLE = "available"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SourceArtifact:
    """
    Durable reference to a source artifact submitted for trace processing.

    The entity stores artifact metadata and a storage-independent key.
    Infrastructure adapters resolve ``storage_key`` to physical content.
    """

    artifact_id: UUID
    tenant_id: str
    trace_id: str
    testcase_id: str | None

    storage_type: ArtifactStorageType
    storage_key: str

    filename: str
    content_type: str | None
    size_bytes: int
    artifact_hash: str

    status: ArtifactStatus

    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        tenant_id = self.tenant_id.strip()
        trace_id = self.trace_id.strip()
        testcase_id = (
            self.testcase_id.strip()
            if self.testcase_id is not None
            else None
        )
        storage_key = self.storage_key.strip()
        filename = self.filename.strip()
        content_type = (
            self.content_type.strip()
            if self.content_type is not None
            else None
        )
        artifact_hash = self.artifact_hash.strip().lower()

        if not tenant_id:
            raise ValueError("tenant_id must not be empty")

        if not trace_id:
            raise ValueError("trace_id must not be empty")

        if testcase_id == "":
            testcase_id = None

        if not storage_key:
            raise ValueError("storage_key must not be empty")

        if not filename:
            raise ValueError("filename must not be empty")

        if content_type == "":
            content_type = None

        if self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")

        if len(artifact_hash) != 64:
            raise ValueError(
                "artifact_hash must be a 64-character SHA-256 hexadecimal value"
            )

        try:
            int(artifact_hash, 16)
        except ValueError as exc:
            raise ValueError(
                "artifact_hash must contain only hexadecimal characters"
            ) from exc

        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")

        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")

        if self.updated_at < self.created_at:
            raise ValueError(
                "updated_at must not be earlier than created_at"
            )

        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "trace_id", trace_id)
        object.__setattr__(self, "testcase_id", testcase_id)
        object.__setattr__(self, "storage_key", storage_key)
        object.__setattr__(self, "filename", filename)
        object.__setattr__(self, "content_type", content_type)
        object.__setattr__(self, "artifact_hash", artifact_hash)

    @property
    def id(self) -> UUID:
        """Return the artifact identifier using repository-style naming."""
        return self.artifact_id

    @property
    def is_available(self) -> bool:
        """Return whether the artifact is available for processing."""
        return self.status == ArtifactStatus.AVAILABLE

    def mark_processing(
        self,
        *,
        changed_at: datetime | None = None,
    ) -> SourceArtifact:
        """Return the artifact in processing state."""
        return self._with_status(
            ArtifactStatus.PROCESSING,
            changed_at=changed_at,
        )

    def mark_processed(
        self,
        *,
        changed_at: datetime | None = None,
    ) -> SourceArtifact:
        """Return the artifact in processed state."""
        return self._with_status(
            ArtifactStatus.PROCESSED,
            changed_at=changed_at,
        )

    def mark_failed(
        self,
        *,
        changed_at: datetime | None = None,
    ) -> SourceArtifact:
        """Return the artifact in failed state."""
        return self._with_status(
            ArtifactStatus.FAILED,
            changed_at=changed_at,
        )

    def _with_status(
        self,
        status: ArtifactStatus,
        *,
        changed_at: datetime | None,
    ) -> SourceArtifact:
        timestamp = changed_at or datetime.now(timezone.utc)

        if timestamp.tzinfo is None:
            raise ValueError("changed_at must be timezone-aware")

        if timestamp < self.updated_at:
            raise ValueError(
                "changed_at must not be earlier than updated_at"
            )

        return replace(
            self,
            status=status,
            updated_at=timestamp,
        )
