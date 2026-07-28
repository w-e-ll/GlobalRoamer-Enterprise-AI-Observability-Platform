"""Bootstrap wiring for persisted artifact processing."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.application.traces.parse_trace import (
    ParseTrace,
)
from globalroamer_platform.application.traces.process_artifact import (
    ProcessArtifact,
)
from globalroamer_platform.bootstrap.trace_processing import (
    build_process_trace,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_artifact_repository import (
    SQLAlchemyArtifactRepository,
)
from globalroamer_platform.infrastructure.object_storage.local_object_storage import (
    LocalObjectStorage,
)


def build_process_artifact(
    *,
    session: AsyncSession,
    parse_trace: ParseTrace,
    artifact_storage_directory: Path,
    supported_extensions: list[str] | None = None,
    max_file_size_mb: int = 100,
) -> ProcessArtifact:
    """
    Build the persisted-artifact processing workflow.

    The artifact storage directory is also used as the TraceLoader root.
    This ensures materialized local objects pass TraceLoader path-boundary
    validation.

    The supplied SQLAlchemy session is shared by artifact persistence and
    parsed-trace persistence. The caller remains responsible for committing
    or rolling back the transaction.
    """

    process_trace = build_process_trace(
        session=session,
        parse_trace=parse_trace,
        trace_directory=(
            artifact_storage_directory
        ),
        supported_extensions=(
            supported_extensions
        ),
        max_file_size_mb=max_file_size_mb,
    )

    return ProcessArtifact(
        artifact_repository=(
            SQLAlchemyArtifactRepository(
                session=session,
            )
        ),
        object_storage=LocalObjectStorage(
            root_directory=(
                artifact_storage_directory
            ),
        ),
        process_trace=process_trace,
    )
