"""Application port for artifact content storage."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Protocol


class ObjectStorage(Protocol):
    """
    Storage abstraction for artifact binary content.

    Implementations may use:
    - local filesystem
    - S3
    - MinIO
    - cloud object storage
    """

    async def write(
        self,
        *,
        storage_key: str,
        content: BinaryIO,
    ) -> None:
        """
        Persist artifact content under a durable storage key.

        Args:
            storage_key:
                Storage-specific object key.

            content:
                Binary stream positioned at the beginning of the
                artifact content.

        Raises:
            ValueError:
                If the storage key is invalid.

            OSError:
                If the content cannot be persisted.
        """
        ...

    async def open(
        self,
        storage_key: str,
    ) -> BinaryIO:
        """
        Open artifact content as a binary stream.

        The caller owns the returned stream and is responsible for closing it.

        Args:
            storage_key:
                Storage-specific object key.

        Returns:
            Binary stream containing artifact content.

        Raises:
            FileNotFoundError:
                If the stored object does not exist.

            ValueError:
                If the storage key is invalid.

            OSError:
                If the stored content cannot be opened.
        """
        ...

    async def exists(
        self,
        storage_key: str,
    ) -> bool:
        """
        Check whether an artifact exists.

        Args:
            storage_key:
                Storage-specific object key.

        Returns:
            True if the object exists, otherwise False.

        Raises:
            ValueError:
                If the storage key is invalid.
        """
        ...

    async def materialize(
        self,
        storage_key: str,
    ) -> Path:
        """
        Resolve artifact content to a local filesystem path.

        A local-filesystem implementation may return the existing object path.
        A remote implementation may download the object into controlled
        temporary storage.

        The returned path must be suitable for path-based processors such as
        TraceLoader.

        Args:
            storage_key:
                Storage-specific object key.

        Returns:
            Local filesystem path containing the artifact content.

        Raises:
            FileNotFoundError:
                If the stored object does not exist.

            ValueError:
                If the storage key is invalid.

            OSError:
                If the object cannot be materialized.
        """
        ...
