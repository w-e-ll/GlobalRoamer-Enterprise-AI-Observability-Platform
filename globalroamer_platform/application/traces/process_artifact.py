"""Application use case for processing a persisted source artifact."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from globalroamer_platform.application.ports.artifact_repository import (
    ArtifactRepository,
)
from globalroamer_platform.application.ports.object_storage import (
    ObjectStorage,
)
from globalroamer_platform.application.traces.process_trace import (
    ProcessTrace,
    ProcessTraceCommand,
    ProcessTraceResult,
)
from globalroamer_platform.domain.entities.source_artifact import (
    ArtifactStatus,
)


@dataclass(frozen=True, slots=True)
class ProcessArtifactCommand:
    """Input for processing one persisted source artifact."""

    artifact_id: UUID
    tenant_id: str

    def __post_init__(self) -> None:
        tenant_id = self.tenant_id.strip()

        if not tenant_id:
            raise ValueError(
                "tenant_id must not be empty"
            )

        object.__setattr__(
            self,
            "tenant_id",
            tenant_id,
        )


@dataclass(frozen=True, slots=True)
class ProcessArtifactResult:
    """Result returned after processing one persisted artifact."""

    artifact_id: UUID
    artifact_status: ArtifactStatus
    trace_result: ProcessTraceResult


class ProcessArtifact:
    """
    Resolve and process one persisted source artifact.

    Responsibilities:

    - load artifact metadata from the repository;
    - verify tenant ownership;
    - transition the artifact to processing;
    - materialize its content through ObjectStorage;
    - delegate parsing and persistence to ProcessTrace;
    - transition the artifact to processed.

    This use case does not commit the transaction. The caller owns commit
    and rollback so artifact state, parsed-trace persistence, and outgoing
    outbox messages can participate in one transaction.
    """

    def __init__(
        self,
        *,
        artifact_repository: ArtifactRepository,
        object_storage: ObjectStorage,
        process_trace: ProcessTrace,
    ) -> None:
        self._artifact_repository = (
            artifact_repository
        )
        self._object_storage = object_storage
        self._process_trace = process_trace

    async def execute(
        self,
        command: ProcessArtifactCommand,
    ) -> ProcessArtifactResult:
        if not isinstance(
            command,
            ProcessArtifactCommand,
        ):
            raise TypeError(
                "command must be a "
                "ProcessArtifactCommand"
            )

        artifact = await self._artifact_repository.get(
            command.artifact_id,
        )

        if artifact.tenant_id != command.tenant_id:
            raise ValueError(
                "Artifact tenant does not match "
                "the event tenant"
            )

        if artifact.status != ArtifactStatus.AVAILABLE:
            raise ValueError(
                "Source artifact is not available for "
                "processing: "
                f"artifact_id={artifact.artifact_id}, "
                f"status={artifact.status.value!r}"
            )

        processing_artifact = (
            artifact.mark_processing()
        )

        await self._artifact_repository.update(
            processing_artifact,
        )

        source_path = (
            await self._object_storage.materialize(
                processing_artifact.storage_key,
            )
        )

        trace_result = await self._process_trace.execute(
            ProcessTraceCommand(
                source_path=source_path,
                tenant_id=(
                    processing_artifact.tenant_id
                ),
                trace_id=(
                    processing_artifact.trace_id
                ),
                testcase_id=(
                    processing_artifact.testcase_id
                ),
            )
        )

        processed_artifact = (
            processing_artifact.mark_processed()
        )

        await self._artifact_repository.update(
            processed_artifact,
        )

        return ProcessArtifactResult(
            artifact_id=(
                processed_artifact.artifact_id
            ),
            artifact_status=(
                processed_artifact.status
            ),
            trace_result=trace_result,
        )
