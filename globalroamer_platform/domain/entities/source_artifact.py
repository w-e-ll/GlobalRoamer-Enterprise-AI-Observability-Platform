"""Domain entity representing a trace source artifact."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
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
    Reference to an uploaded trace artifact.

    The entity intentionally does not expose a physical path.
    Consumers resolve the artifact through an ArtifactRepository.
    """

    artifact_id: UUID
    tenant_id: str

    storage_type: ArtifactStorageType
    storage_key: str

    filename: str
    content_type: str | None
    size_bytes: int

    status: ArtifactStatus

    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        tenant_id = self.tenant_id.strip()
        storage_key = self.storage_key.strip()
        filename = self.filename.strip()

        if not tenant_id:
            raise ValueError(
                "tenant_id must not be empty"
            )

        if not storage_key:
            raise ValueError(
                "storage_key must not be empty"
            )

        if not filename:
            raise ValueError(
                "filename must not be empty"
            )

        if self.size_bytes < 0:
            raise ValueError(
                "size_bytes must not be negative"
            )

        object.__setattr__(
            self,
            "tenant_id",
            tenant_id,
        )

        object.__setattr__(
            self,
            "storage_key",
            storage_key,
        )

        object.__setattr__(
            self,
            "filename",
            filename,
        )

    @property
    def is_available(self) -> bool:
        """Return whether the artifact can be processed."""
        return self.status == ArtifactStatus.AVAILABLE

    def mark_processing(
        self,
    ) -> SourceArtifact:
        """Return artifact in processing state."""
        return SourceArtifact(
            artifact_id=self.artifact_id,
            tenant_id=self.tenant_id,
            storage_type=self.storage_type,
            storage_key=self.storage_key,
            filename=self.filename,
            content_type=self.content_type,
            size_bytes=self.size_bytes,
            status=ArtifactStatus.PROCESSING,
            created_at=self.created_at,
            updated_at=datetime.utcnow(),
        )
