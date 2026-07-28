# globalroamer_platform/infrastructure/object_storage/local_object_storage.py

"""Local-filesystem implementation of object storage."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO

from globalroamer_platform.application.ports.object_storage import (
    ObjectStorage,
)


class LocalObjectStorage(ObjectStorage):
    """
    Store artifact content under a controlled local directory.

    Storage keys are relative, storage-independent identifiers such as:

        tenant-a/2026/07/28/<artifact-id>/sample_trace.csv

    Absolute paths, parent-directory traversal, empty path components,
    and paths escaping the configured root are rejected.

    Writes are performed through a temporary file in the destination
    directory and finalized using an atomic filesystem replacement.
    """

    def __init__(
        self,
        *,
        root_directory: Path,
    ) -> None:
        root_directory = (
            root_directory
            .expanduser()
            .resolve()
        )

        self._root_directory = root_directory

    @property
    def root_directory(self) -> Path:
        """Return the configured artifact-storage root."""

        return self._root_directory

    async def write(
        self,
        *,
        storage_key: str,
        content: BinaryIO,
    ) -> None:
        """
        Persist binary content under a durable storage key.

        Existing objects with the same key are replaced atomically.

        Args:
            storage_key:
                Relative object key inside the configured storage root.

            content:
                Readable binary stream containing the artifact content.

        Raises:
            ValueError:
                If the storage key or content stream is invalid.

            OSError:
                If the destination directory cannot be created or the
                content cannot be persisted.
        """

        destination = self._resolve_storage_key(
            storage_key,
        )

        self._validate_content_stream(
            content,
        )

        await asyncio.to_thread(
            self._write_sync,
            destination,
            content,
        )

    async def open(
        self,
        storage_key: str,
    ) -> BinaryIO:
        """
        Open stored artifact content as a binary stream.

        The caller owns the returned stream and must close it.

        Args:
            storage_key:
                Relative object key inside the configured storage root.

        Returns:
            Readable binary stream.

        Raises:
            FileNotFoundError:
                If the stored object does not exist.

            IsADirectoryError:
                If the storage key resolves to a directory.

            ValueError:
                If the storage key is invalid.

            OSError:
                If the object cannot be opened.
        """

        source_path = self._resolve_storage_key(
            storage_key,
        )

        return await asyncio.to_thread(
            self._open_sync,
            source_path,
        )

    async def exists(
        self,
        storage_key: str,
    ) -> bool:
        """
        Return whether a regular file exists for the storage key.

        Directories are not considered stored objects.
        """

        source_path = self._resolve_storage_key(
            storage_key,
        )

        return await asyncio.to_thread(
            source_path.is_file,
        )

    async def materialize(
        self,
        storage_key: str,
    ) -> Path:
        """
        Resolve stored content to its existing local filesystem path.

        Because this adapter already stores objects locally, no download
        or temporary copy is required.

        Args:
            storage_key:
                Relative object key inside the configured storage root.

        Returns:
            Absolute path to the stored regular file.

        Raises:
            FileNotFoundError:
                If the object does not exist.

            IsADirectoryError:
                If the key resolves to a directory.

            ValueError:
                If the storage key is invalid.
        """

        source_path = self._resolve_storage_key(
            storage_key,
        )

        await asyncio.to_thread(
            self._validate_existing_object,
            source_path,
        )

        return source_path

    def _resolve_storage_key(
        self,
        storage_key: str,
    ) -> Path:
        """
        Convert a storage key into a safe absolute path.

        The returned path is guaranteed to remain inside the configured
        root directory.
        """

        normalized_key = self._validate_storage_key(
            storage_key,
        )

        candidate = (
            self._root_directory
            / Path(normalized_key)
        ).resolve(strict=False)

        try:
            candidate.relative_to(
                self._root_directory,
            )
        except ValueError as exc:
            raise ValueError(
                "Storage key resolves outside the configured "
                f"storage root: {storage_key!r}"
            ) from exc

        return candidate

    @staticmethod
    def _validate_storage_key(
        storage_key: str,
    ) -> str:
        if not isinstance(storage_key, str):
            raise ValueError(
                "storage_key must be a string"
            )

        normalized_key = storage_key.strip()

        if not normalized_key:
            raise ValueError(
                "storage_key must not be empty"
            )

        if "\x00" in normalized_key:
            raise ValueError(
                "storage_key must not contain null bytes"
            )

        normalized_key = normalized_key.replace(
            "\\",
            "/",
        )

        key_path = Path(normalized_key)

        if key_path.is_absolute():
            raise ValueError(
                "storage_key must be relative"
            )

        parts = normalized_key.split("/")

        if any(
            part in {"", ".", ".."}
            for part in parts
        ):
            raise ValueError(
                "storage_key contains an invalid path component"
            )

        return normalized_key

    @staticmethod
    def _validate_content_stream(
        content: BinaryIO,
    ) -> None:
        if content is None:
            raise ValueError(
                "content must not be None"
            )

        read_method = getattr(
            content,
            "read",
            None,
        )

        if not callable(read_method):
            raise ValueError(
                "content must be a readable binary stream"
            )

        closed = getattr(
            content,
            "closed",
            False,
        )

        if closed:
            raise ValueError(
                "content stream is closed"
            )

    @staticmethod
    def _write_sync(
        destination: Path,
        content: BinaryIO,
    ) -> None:
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(
                    temporary_file.name,
                )

                shutil.copyfileobj(
                    content,
                    temporary_file,
                )

                temporary_file.flush()
                os.fsync(
                    temporary_file.fileno(),
                )

            os.replace(
                temporary_path,
                destination,
            )

        except Exception:
            if (
                temporary_path is not None
                and temporary_path.exists()
            ):
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

            raise

    @staticmethod
    def _open_sync(
        source_path: Path,
    ) -> BinaryIO:
        LocalObjectStorage._validate_existing_object(
            source_path,
        )

        return source_path.open(
            "rb",
        )

    @staticmethod
    def _validate_existing_object(
        source_path: Path,
    ) -> None:
        if not source_path.exists():
            raise FileNotFoundError(
                f"Stored object was not found: {source_path}"
            )

        if source_path.is_dir():
            raise IsADirectoryError(
                f"Stored object path is a directory: {source_path}"
            )

        if not source_path.is_file():
            raise OSError(
                f"Stored object is not a regular file: {source_path}"
            )
