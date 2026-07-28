"""SQLAlchemy implementation of the source artifact repository."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.application.ports.artifact_repository import (
    ArtifactRepository,
)
from globalroamer_platform.domain.entities.source_artifact import (
    ArtifactStatus,
    ArtifactStorageType,
    SourceArtifact,
)
from globalroamer_platform.infrastructure.database.models import (
    SourceArtifactModel,
)


logger = logging.getLogger(__name__)


class SQLAlchemyArtifactRepository(ArtifactRepository):
    """Persist and retrieve source artifacts using SQLAlchemy."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get(
        self,
        artifact_id: UUID,
    ) -> SourceArtifact:
        """
        Retrieve an artifact by identifier.

        Raises:
            FileNotFoundError: If no artifact exists with the identifier.
        """
        logger.debug(
            "Loading source artifact artifact_id=%s",
            artifact_id,
        )

        model = await self._session.get(
            SourceArtifactModel,
            artifact_id,
        )

        if model is None:
            logger.debug(
                "Source artifact not found artifact_id=%s",
                artifact_id,
            )
            raise FileNotFoundError(
                f"Source artifact was not found: {artifact_id}"
            )

        logger.debug(
            "Source artifact loaded artifact_id=%s tenant_id=%s "
            "trace_id=%s status=%s",
            model.id,
            model.tenant_id,
            model.trace_id,
            model.status,
        )

        return self._to_entity(model)

    async def add(
        self,
        artifact: SourceArtifact,
    ) -> None:
        """Add a new source artifact to the current transaction."""
        if not isinstance(artifact, SourceArtifact):
            raise TypeError(
                "artifact must be a SourceArtifact"
            )

        logger.debug(
            "Persisting source artifact artifact_id=%s tenant_id=%s "
            "trace_id=%s storage_type=%s",
            artifact.artifact_id,
            artifact.tenant_id,
            artifact.trace_id,
            artifact.storage_type.value,
        )

        model = self._to_model(artifact)

        self._session.add(model)
        await self._session.flush()

        logger.info(
            "Source artifact persisted artifact_id=%s tenant_id=%s "
            "trace_id=%s status=%s",
            model.id,
            model.tenant_id,
            model.trace_id,
            model.status,
        )

    async def update(
        self,
        artifact: SourceArtifact,
    ) -> None:
        """Persist the current state of an existing source artifact."""
        if not isinstance(artifact, SourceArtifact):
            raise TypeError(
                "artifact must be a SourceArtifact"
            )

        logger.debug(
            "Updating source artifact artifact_id=%s status=%s",
            artifact.artifact_id,
            artifact.status.value,
        )

        model = await self._session.get(
            SourceArtifactModel,
            artifact.artifact_id,
        )

        if model is None:
            logger.warning(
                "Cannot update source artifact because it does not exist "
                "artifact_id=%s",
                artifact.artifact_id,
            )
            raise FileNotFoundError(
                "Source artifact was not found: "
                f"{artifact.artifact_id}"
            )

        self._update_model(
            model=model,
            artifact=artifact,
        )

        await self._session.flush()

        logger.info(
            "Source artifact updated artifact_id=%s tenant_id=%s "
            "trace_id=%s status=%s",
            model.id,
            model.tenant_id,
            model.trace_id,
            model.status,
        )

    @staticmethod
    def _to_model(
        artifact: SourceArtifact,
    ) -> SourceArtifactModel:
        """Convert a domain entity into a SQLAlchemy model."""
        return SourceArtifactModel(
            id=artifact.artifact_id,
            tenant_id=artifact.tenant_id,
            trace_id=artifact.trace_id,
            testcase_id=artifact.testcase_id,
            filename=artifact.filename,
            storage_type=artifact.storage_type.value,
            storage_key=artifact.storage_key,
            content_type=artifact.content_type,
            size_bytes=artifact.size_bytes,
            artifact_hash=artifact.artifact_hash,
            status=artifact.status.value,
            created_at=artifact.created_at,
            updated_at=artifact.updated_at,
        )

    @staticmethod
    def _to_entity(
        model: SourceArtifactModel,
    ) -> SourceArtifact:
        """Convert a SQLAlchemy model into a domain entity."""
        return SourceArtifact(
            artifact_id=model.id,
            tenant_id=model.tenant_id,
            trace_id=model.trace_id,
            testcase_id=model.testcase_id,
            storage_type=ArtifactStorageType(
                model.storage_type
            ),
            storage_key=model.storage_key,
            filename=model.filename,
            content_type=model.content_type,
            size_bytes=model.size_bytes,
            artifact_hash=model.artifact_hash,
            status=ArtifactStatus(model.status),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _update_model(
        *,
        model: SourceArtifactModel,
        artifact: SourceArtifact,
    ) -> None:
        """Copy the entity state to an existing persistence model."""
        model.tenant_id = artifact.tenant_id
        model.trace_id = artifact.trace_id
        model.testcase_id = artifact.testcase_id
        model.filename = artifact.filename
        model.storage_type = artifact.storage_type.value
        model.storage_key = artifact.storage_key
        model.content_type = artifact.content_type
        model.size_bytes = artifact.size_bytes
        model.artifact_hash = artifact.artifact_hash
        model.status = artifact.status.value
        model.created_at = artifact.created_at
        model.updated_at = artifact.updated_at
