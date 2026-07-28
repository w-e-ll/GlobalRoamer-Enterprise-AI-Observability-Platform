"""Application use case for submitting trace artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from globalroamer_platform.application.ports.artifact_repository import (
    ArtifactRepository,
)
from globalroamer_platform.application.ports.object_storage import (
    ObjectStorage,
)
from globalroamer_platform.application.ports.outbox_repository import (
    OutboxRepository,
)
from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
)
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


_SAFE_STORAGE_COMPONENT_PATTERN = re.compile(
    r"[^A-Za-z0-9._-]+"
)


@dataclass(frozen=True, slots=True)
class SubmitTraceCommand:
    """Input for submitting one trace artifact."""

    source_path: Path
    tenant_id: str
    trace_id: str
    testcase_id: str | None
    correlation_id: str

    def __post_init__(self) -> None:
        source_path = Path(
            self.source_path,
        ).expanduser()

        tenant_id = self.tenant_id.strip()
        trace_id = self.trace_id.strip()

        testcase_id = (
            self.testcase_id.strip()
            if self.testcase_id is not None
            else None
        )

        correlation_id = (
            self.correlation_id.strip()
        )

        if not str(source_path).strip():
            raise ValueError(
                "source_path must not be empty"
            )

        if not tenant_id:
            raise ValueError(
                "tenant_id must not be empty"
            )

        if not trace_id:
            raise ValueError(
                "trace_id must not be empty"
            )

        if testcase_id == "":
            testcase_id = None

        if not correlation_id:
            raise ValueError(
                "correlation_id must not be empty"
            )

        object.__setattr__(
            self,
            "source_path",
            source_path,
        )
        object.__setattr__(
            self,
            "tenant_id",
            tenant_id,
        )
        object.__setattr__(
            self,
            "trace_id",
            trace_id,
        )
        object.__setattr__(
            self,
            "testcase_id",
            testcase_id,
        )
        object.__setattr__(
            self,
            "correlation_id",
            correlation_id,
        )


@dataclass(frozen=True, slots=True)
class SubmitTraceResult:
    """Result returned after accepting a trace artifact."""

    artifact_id: UUID
    submission_event_id: UUID
    outbox_message_id: UUID

    tenant_id: str
    trace_id: str
    testcase_id: str | None
    correlation_id: str

    storage_key: str
    status: str


@dataclass(frozen=True, slots=True)
class _SourceFileMetadata:
    """Metadata calculated from the submitted source file."""

    resolved_path: Path
    filename: str
    content_type: str | None
    size_bytes: int
    artifact_hash: str


class SubmitTrace:
    """
    Persist an artifact and publish its processing event.

    Artifact metadata and the outgoing event are added through repositories
    sharing the same database transaction. The outer API transaction boundary
    owns commit and rollback.

    Object content is written before the database transaction commits. Until
    ObjectStorage supports deletion, a failed database transaction may leave
    an unreferenced object that can later be removed by maintenance.
    """

    PRODUCER = (
        "globalroamer.trace-submission-api"
    )

    def __init__(
        self,
        *,
        artifact_repository: ArtifactRepository,
        object_storage: ObjectStorage,
        outbox_repository: OutboxRepository,
    ) -> None:
        self._artifact_repository = (
            artifact_repository
        )
        self._object_storage = object_storage
        self._outbox_repository = (
            outbox_repository
        )

    async def execute(
        self,
        command: SubmitTraceCommand,
    ) -> SubmitTraceResult:
        if not isinstance(
            command,
            SubmitTraceCommand,
        ):
            raise TypeError(
                "command must be a "
                "SubmitTraceCommand"
            )

        file_metadata = await asyncio.to_thread(
            self._inspect_source_file,
            command.source_path,
        )

        artifact_id = uuid4()
        timestamp = datetime.now(
            timezone.utc,
        )

        storage_key = self._build_storage_key(
            artifact_id=artifact_id,
            tenant_id=command.tenant_id,
            filename=file_metadata.filename,
            created_at=timestamp,
        )

        with file_metadata.resolved_path.open(
            "rb",
        ) as content:
            await self._object_storage.write(
                storage_key=storage_key,
                content=content,
            )

        artifact = SourceArtifact(
            artifact_id=artifact_id,
            tenant_id=command.tenant_id,
            trace_id=command.trace_id,
            testcase_id=command.testcase_id,
            storage_type=(
                ArtifactStorageType.FILESYSTEM
            ),
            storage_key=storage_key,
            filename=file_metadata.filename,
            content_type=(
                file_metadata.content_type
            ),
            size_bytes=(
                file_metadata.size_bytes
            ),
            artifact_hash=(
                file_metadata.artifact_hash
            ),
            status=ArtifactStatus.AVAILABLE,
            created_at=timestamp,
            updated_at=timestamp,
        )

        await self._artifact_repository.add(
            artifact,
        )

        event = EventEnvelope(
            event_id=uuid4(),
            event_type=(
                TRACE_ARTIFACT_RECEIVED
            ),
            event_version=1,
            correlation_id=(
                command.correlation_id
            ),
            causation_id=None,
            tenant_id=command.tenant_id,
            occurred_at=timestamp,
            producer=self.PRODUCER,
            payload={
                "artifact_id": str(
                    artifact.artifact_id
                ),
                "trace_id": (
                    artifact.trace_id
                ),
                "testcase_id": (
                    artifact.testcase_id
                ),
            },
        )

        outbox_message = OutboxMessage.create(
            event=event,
        )

        await self._outbox_repository.add(
            outbox_message,
        )

        return SubmitTraceResult(
            artifact_id=(
                artifact.artifact_id
            ),
            submission_event_id=(
                event.event_id
            ),
            outbox_message_id=(
                outbox_message.id
            ),
            tenant_id=artifact.tenant_id,
            trace_id=artifact.trace_id,
            testcase_id=(
                artifact.testcase_id
            ),
            correlation_id=(
                command.correlation_id
            ),
            storage_key=(
                artifact.storage_key
            ),
            status="accepted",
        )

    @staticmethod
    def _inspect_source_file(
        source_path: Path,
    ) -> _SourceFileMetadata:
        resolved_path = source_path.resolve(
            strict=False,
        )

        if not resolved_path.exists():
            raise FileNotFoundError(
                "Trace source file was not found: "
                f"{resolved_path}"
            )

        if resolved_path.is_dir():
            raise IsADirectoryError(
                "Trace source path is a directory: "
                f"{resolved_path}"
            )

        if not resolved_path.is_file():
            raise OSError(
                "Trace source path is not a "
                "regular file: "
                f"{resolved_path}"
            )

        stat_result = resolved_path.stat()

        artifact_hash = (
            SubmitTrace._calculate_sha256(
                resolved_path,
            )
        )

        content_type, _ = (
            mimetypes.guess_type(
                resolved_path.name,
            )
        )

        return _SourceFileMetadata(
            resolved_path=resolved_path,
            filename=resolved_path.name,
            content_type=content_type,
            size_bytes=stat_result.st_size,
            artifact_hash=artifact_hash,
        )

    @staticmethod
    def _calculate_sha256(
        source_path: Path,
    ) -> str:
        digest = hashlib.sha256()

        with source_path.open(
            "rb",
        ) as source_file:
            while chunk := source_file.read(
                1024 * 1024,
            ):
                digest.update(chunk)

        return digest.hexdigest()

    @classmethod
    def _build_storage_key(
        cls,
        *,
        artifact_id: UUID,
        tenant_id: str,
        filename: str,
        created_at: datetime,
    ) -> str:
        safe_tenant_id = (
            cls._safe_storage_component(
                tenant_id,
                fallback="tenant",
            )
        )

        safe_filename = (
            cls._safe_storage_component(
                Path(filename).name,
                fallback="artifact.bin",
            )
        )

        return (
            f"{safe_tenant_id}/"
            f"{created_at:%Y/%m/%d}/"
            f"{artifact_id}/"
            f"{safe_filename}"
        )

    @staticmethod
    def _safe_storage_component(
        value: str,
        *,
        fallback: str,
    ) -> str:
        normalized = (
            _SAFE_STORAGE_COMPONENT_PATTERN.sub(
                "_",
                value.strip(),
            ).strip("._")
        )

        return normalized or fallback
