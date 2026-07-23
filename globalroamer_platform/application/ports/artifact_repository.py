"""Application port for resolving source artifacts."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from globalroamer_platform.domain.entities.source_artifact import (
    SourceArtifact,
)


class ArtifactRepository(Protocol):
    """
    Repository contract for source artifact resolution.

    Implementations belong to infrastructure layer.

    Examples:
    - PostgreSQL artifact repository
    - filesystem-backed repository
    - S3/object-storage repository
    """

    async def get(
        self,
        artifact_id: UUID,
    ) -> SourceArtifact:
        """
        Retrieve an artifact by identifier.

        Args:
            artifact_id: Unique artifact identifier.

        Returns:
            SourceArtifact domain entity.

        Raises:
            FileNotFoundError:
                If the artifact does not exist.
        """
        ...

    async def add(
        self,
        artifact: SourceArtifact,
    ) -> None:
        """
        Persist a new artifact reference.

        Args:
            artifact: Artifact entity to store.
        """
        ...

    async def update(
        self,
        artifact: SourceArtifact,
    ) -> None:
        """
        Persist an updated artifact lifecycle state.

        Args:
            artifact: Updated artifact entity.
        """
        ...
