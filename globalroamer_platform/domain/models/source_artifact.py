# globalroamer_platform/domain/models/source_artifact.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4


class SourceArtifactType(StrEnum):
    """Supported categories of source artifacts."""

    TRACE = "trace"
    RESULT = "result"
    REPORT = "report"
    TEMPLATE = "template"
    CAMPAIGN_METADATA = "campaign_metadata"


@dataclass(frozen=True, slots=True)
class SourceArtifact:
    """
    Describe a source file accepted by the processing pipeline.

    This domain model contains artifact identity and immutable metadata.
    It does not parse, normalize or otherwise interpret file content.
    """

    id: UUID
    artifact_type: SourceArtifactType

    source_path: Path
    filename: str
    extension: str

    size_bytes: int
    checksum_sha256: str

    loaded_at: datetime

    content_type: str | None = None
    tenant_id: str | None = None
    trace_id: str | None = None
    testcase_id: str | None = None

    def __post_init__(self) -> None:
        normalized_path = (
            self.source_path
            .expanduser()
            .resolve()
        )
        normalized_filename = self.filename.strip()
        normalized_extension = (
            self.extension
            .strip()
            .lower()
        )
        normalized_checksum = (
            self.checksum_sha256
            .strip()
            .lower()
        )

        if not normalized_filename:
            raise ValueError(
                "Source artifact filename must not be empty"
            )

        if not normalized_extension:
            raise ValueError(
                "Source artifact extension must not be empty"
            )

        if not normalized_extension.startswith("."):
            raise ValueError(
                "Source artifact extension must start with '.'"
            )

        if self.size_bytes < 0:
            raise ValueError(
                "Source artifact size must not be negative"
            )

        if len(normalized_checksum) != 64:
            raise ValueError(
                "Source artifact SHA-256 checksum must contain "
                "exactly 64 hexadecimal characters"
            )

        try:
            int(normalized_checksum, 16)
        except ValueError as exc:
            raise ValueError(
                "Source artifact SHA-256 checksum must be hexadecimal"
            ) from exc

        if self.loaded_at.tzinfo is None:
            raise ValueError(
                "Source artifact loaded_at must be timezone-aware"
            )

        object.__setattr__(
            self,
            "source_path",
            normalized_path,
        )
        object.__setattr__(
            self,
            "filename",
            normalized_filename,
        )
        object.__setattr__(
            self,
            "extension",
            normalized_extension,
        )
        object.__setattr__(
            self,
            "checksum_sha256",
            normalized_checksum,
        )
        object.__setattr__(
            self,
            "content_type",
            _normalize_optional_text(
                self.content_type
            ),
        )
        object.__setattr__(
            self,
            "tenant_id",
            _normalize_optional_text(
                self.tenant_id
            ),
        )
        object.__setattr__(
            self,
            "trace_id",
            _normalize_optional_text(
                self.trace_id
            ),
        )
        object.__setattr__(
            self,
            "testcase_id",
            _normalize_optional_text(
                self.testcase_id
            ),
        )

    @classmethod
    def create(
        cls,
        *,
        artifact_type: SourceArtifactType,
        source_path: Path,
        size_bytes: int,
        checksum_sha256: str,
        content_type: str | None = None,
        tenant_id: str | None = None,
        trace_id: str | None = None,
        testcase_id: str | None = None,
        loaded_at: datetime | None = None,
        artifact_id: UUID | None = None,
    ) -> SourceArtifact:
        """Create a source artifact from validated loader metadata."""

        normalized_path = (
            source_path
            .expanduser()
            .resolve()
        )

        return cls(
            id=artifact_id or uuid4(),
            artifact_type=artifact_type,
            source_path=normalized_path,
            filename=normalized_path.name,
            extension=normalized_path.suffix.lower(),
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256,
            loaded_at=loaded_at or datetime.now(timezone.utc),
            content_type=content_type,
            tenant_id=tenant_id,
            trace_id=trace_id,
            testcase_id=testcase_id,
        )

    @property
    def size_megabytes(self) -> float:
        """Return artifact size in mebibytes."""

        return self.size_bytes / (1024 * 1024)


def _normalize_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized_value = value.strip()

    return normalized_value or None
