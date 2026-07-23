"""Application port for artifact content storage."""

from __future__ import annotations

from typing import BinaryIO, Protocol


class ObjectStorage(Protocol):
    """
    Storage abstraction for artifact content.

    Implementations may use:
    - local filesystem
    - S3
    - MinIO
    - cloud object storage
    """

    async def open(
        self,
        storage_key: str,
    ) -> BinaryIO:
        """
        Open artifact content stream.

        Args:
            storage_key: Storage-specific object key.

        Returns:
            Binary stream containing artifact content.
        """
        ...

    async def exists(
        self,
        storage_key: str,
    ) -> bool:
        """
        Check whether an artifact exists.

        Args:
            storage_key: Storage-specific object key.

        Returns:
            True if object exists.
        """
        ...
