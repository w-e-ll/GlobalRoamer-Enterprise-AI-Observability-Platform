"""Bootstrap wiring for asynchronous trace submission."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.application.traces.submit_trace import (
    SubmitTrace,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_artifact_repository import (
    SQLAlchemyArtifactRepository,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
)
from globalroamer_platform.infrastructure.object_storage.local_object_storage import (
    LocalObjectStorage,
)


def build_submit_trace(
    *,
    session: AsyncSession,
    artifact_storage_directory: Path,
) -> SubmitTrace:
    """
    Build the asynchronous trace-submission dependency graph.

    Artifact metadata and outbox messages share the supplied SQLAlchemy
    session and therefore participate in the same database transaction.
    """

    return SubmitTrace(
        artifact_repository=SQLAlchemyArtifactRepository(
            session=session,
        ),
        object_storage=LocalObjectStorage(
            root_directory=artifact_storage_directory,
        ),
        outbox_repository=SQLAlchemyOutboxRepository(
            session=session,
        ),
    )
