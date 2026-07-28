"""Integration-test helpers for persisted trace artifacts."""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.domain.entities.source_artifact import (
    ArtifactStatus,
    ArtifactStorageType,
    SourceArtifact,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_ARTIFACT_RECEIVED,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_artifact_repository import (
    SQLAlchemyArtifactRepository,
)
from globalroamer_platform.infrastructure.object_storage.local_object_storage import (
    LocalObjectStorage,
)


@dataclass(frozen=True, slots=True)
class PersistedTestArtifact:
    """Persisted artifact and event prepared for a worker test."""

    artifact: SourceArtifact
    event: EventEnvelope
    storage_directory: Path


async def create_persisted_test_artifact(
    *,
    session: AsyncSession,
    source_path: Path,
    storage_directory: Path,
    tenant_id: str,
    trace_id: str,
    testcase_id: str | None,
    correlation_id: str | None = None,
    producer: str = "pytest.integration",
) -> PersistedTestArtifact:
    """
    Store a source file and persist its SourceArtifact metadata.

    The helper deliberately mirrors the production artifact contract:

        source file
            -> LocalObjectStorage
            -> SourceArtifact
            -> TRACE_ARTIFACT_RECEIVED

    The caller owns transaction commit and rollback.
    """

    resolved_source_path = source_path.resolve(
        strict=True,
    )

    if not resolved_source_path.is_file():
        raise ValueError(
            "Test artifact source must be a regular file: "
            f"{resolved_source_path}"
        )

    normalized_tenant_id = tenant_id.strip()
    normalized_trace_id = trace_id.strip()
    normalized_testcase_id = (
        testcase_id.strip()
        if testcase_id is not None
        else None
    )
    normalized_correlation_id = (
        correlation_id.strip()
        if correlation_id is not None
        else str(uuid4())
    )

    if not normalized_tenant_id:
        raise ValueError(
            "tenant_id must not be empty"
        )

    if not normalized_trace_id:
        raise ValueError(
            "trace_id must not be empty"
        )

    if normalized_testcase_id == "":
        normalized_testcase_id = None

    if not normalized_correlation_id:
        raise ValueError(
            "correlation_id must not be empty"
        )

    artifact_id = uuid4()
    timestamp = datetime.now(
        timezone.utc,
    )

    filename = resolved_source_path.name
    storage_key = _build_storage_key(
        artifact_id=artifact_id,
        tenant_id=normalized_tenant_id,
        filename=filename,
        created_at=timestamp,
    )

    storage = LocalObjectStorage(
        root_directory=storage_directory,
    )

    with resolved_source_path.open(
        "rb",
    ) as source_file:
        await storage.write(
            storage_key=storage_key,
            content=source_file,
        )

    content_type, _ = mimetypes.guess_type(
        filename,
    )

    artifact = SourceArtifact(
        artifact_id=artifact_id,
        tenant_id=normalized_tenant_id,
        trace_id=normalized_trace_id,
        testcase_id=normalized_testcase_id,
        storage_type=ArtifactStorageType.FILESYSTEM,
        storage_key=storage_key,
        filename=filename,
        content_type=content_type,
        size_bytes=resolved_source_path.stat().st_size,
        artifact_hash=_calculate_sha256(
            resolved_source_path,
        ),
        status=ArtifactStatus.AVAILABLE,
        created_at=timestamp,
        updated_at=timestamp,
    )

    repository = SQLAlchemyArtifactRepository(
        session=session,
    )

    await repository.add(
        artifact,
    )

    event = EventEnvelope(
        event_id=uuid4(),
        event_type=TRACE_ARTIFACT_RECEIVED,
        event_version=1,
        correlation_id=normalized_correlation_id,
        causation_id=None,
        tenant_id=normalized_tenant_id,
        occurred_at=timestamp,
        producer=producer,
        payload={
            "artifact_id": str(
                artifact.artifact_id,
            ),
            "trace_id": artifact.trace_id,
            "testcase_id": artifact.testcase_id,
        },
    )

    return PersistedTestArtifact(
        artifact=artifact,
        event=event,
        storage_directory=storage_directory,
    )


def _calculate_sha256(
    source_path: Path,
) -> str:
    """Calculate the SHA-256 digest of a source file."""

    digest = hashlib.sha256()

    with source_path.open(
        "rb",
    ) as source_file:
        while chunk := source_file.read(
            1024 * 1024,
        ):
            digest.update(
                chunk,
            )

    return digest.hexdigest()


def _build_storage_key(
    *,
    artifact_id: UUID,
    tenant_id: str,
    filename: str,
    created_at: datetime,
) -> str:
    """Build a deterministic test storage key."""

    safe_tenant_id = _safe_component(
        tenant_id,
        fallback="tenant",
    )

    safe_filename = _safe_component(
        Path(filename).name,
        fallback="artifact.bin",
    )

    return (
        f"{safe_tenant_id}/"
        f"{created_at:%Y/%m/%d}/"
        f"{artifact_id}/"
        f"{safe_filename}"
    )


def _safe_component(
    value: str,
    *,
    fallback: str,
) -> str:
    """Normalize one storage-key component."""

    normalized = "".join(
        character
        if (
            character.isalnum()
            or character in "._-"
        )
        else "_"
        for character in value.strip()
    ).strip("._")

    return normalized or fallback
