# globalroamer_platform/domain/services/trace_loader.py

from __future__ import annotations

import hashlib
import logging
import mimetypes
from pathlib import Path
from typing import Final

from globalroamer_platform.core.exceptions import TraceLoaderError
from globalroamer_platform.domain.models.source_artifact import (
    SourceArtifact,
    SourceArtifactType,
)


logger = logging.getLogger(__name__)


CHECKSUM_BLOCK_SIZE: Final[int] = 1024 * 1024


class TraceLoader:
    """
    Discover, validate and describe source trace files.

    The loader is responsible for filesystem-level ingestion only.
    Parsing, normalization and chunking are handled by separate
    processing services.
    """

    def __init__(
        self,
        *,
        trace_directory: Path,
        supported_extensions: list[str],
        max_file_size_mb: int,
    ) -> None:
        if max_file_size_mb <= 0:
            raise ValueError(
                "max_file_size_mb must be greater than zero"
            )

        normalized_extensions = {
            self._normalize_extension(extension)
            for extension in supported_extensions
        }

        if not normalized_extensions:
            raise ValueError(
                "At least one supported trace extension is required"
            )

        self._trace_directory = (
            trace_directory
            .expanduser()
            .resolve()
        )
        self._supported_extensions = frozenset(
            normalized_extensions
        )
        self._max_file_size_bytes = (
            max_file_size_mb
            * 1024
            * 1024
        )

    @property
    def trace_directory(self) -> Path:
        """Return the configured trace input directory."""

        return self._trace_directory

    @property
    def supported_extensions(self) -> frozenset[str]:
        """Return normalized supported trace extensions."""

        return self._supported_extensions

    @property
    def max_file_size_bytes(self) -> int:
        """Return the configured maximum trace size in bytes."""

        return self._max_file_size_bytes

    def discover_paths(self) -> list[Path]:
        """
        Discover supported trace files in the input directory.

        Files are returned in deterministic filename order. This
        method does not calculate checksums or create artifacts.
        """

        self._validate_trace_directory()

        logger.info(
            "Trace discovery started directory=%s",
            self._trace_directory,
        )

        try:
            paths = sorted(
                (
                    path.resolve()
                    for path in self._trace_directory.iterdir()
                    if (
                        path.is_file()
                        and path.suffix.lower()
                        in self._supported_extensions
                    )
                ),
                key=lambda path: path.name.lower(),
            )

        except OSError as exc:
            logger.exception(
                "Trace discovery failed directory=%s",
                self._trace_directory,
            )
            raise TraceLoaderError(
                "Failed to discover trace files in "
                f"{self._trace_directory}"
            ) from exc

        logger.info(
            "Trace discovery completed directory=%s count=%d",
            self._trace_directory,
            len(paths),
        )

        return paths

    def load(
        self,
        source_path: Path,
        *,
        tenant_id: str | None = None,
        trace_id: str | None = None,
        testcase_id: str | None = None,
    ) -> SourceArtifact:
        """
        Validate a trace source and create immutable artifact metadata.

        The file content is read only to calculate its SHA-256
        checksum. Parsing is deliberately delegated to TraceParser.
        """

        resolved_path = self._resolve_source_path(
            source_path
        )

        logger.info(
            "Trace loading started source_path=%s",
            resolved_path,
        )

        try:
            self._validate_source_file(
                resolved_path
            )

            size_bytes = resolved_path.stat().st_size
            checksum_sha256 = self._calculate_sha256(
                resolved_path
            )
            content_type = self._detect_content_type(
                resolved_path
            )

            artifact = SourceArtifact.create(
                artifact_type=SourceArtifactType.TRACE,
                source_path=resolved_path,
                size_bytes=size_bytes,
                checksum_sha256=checksum_sha256,
                content_type=content_type,
                tenant_id=tenant_id,
                trace_id=trace_id,
                testcase_id=testcase_id,
            )

        except TraceLoaderError:
            raise

        except OSError as exc:
            logger.exception(
                "Trace loading failed source_path=%s",
                resolved_path,
            )
            raise TraceLoaderError(
                f"Failed to load trace source: {resolved_path}"
            ) from exc

        logger.info(
            "Trace loading completed source_path=%s "
            "size_bytes=%d checksum_sha256=%s",
            artifact.source_path,
            artifact.size_bytes,
            artifact.checksum_sha256,
        )

        return artifact

    def load_discovered(
        self,
        *,
        tenant_id: str | None = None,
    ) -> list[SourceArtifact]:
        """
        Discover and load every supported trace in the directory.

        A failure in one source stops the operation. Batch-level
        partial-failure handling belongs in an application workflow.
        """

        return [
            self.load(
                source_path,
                tenant_id=tenant_id,
            )
            for source_path in self.discover_paths()
        ]

    def _validate_trace_directory(self) -> None:
        if not self._trace_directory.exists():
            raise TraceLoaderError(
                "Trace input directory does not exist: "
                f"{self._trace_directory}"
            )

        if not self._trace_directory.is_dir():
            raise TraceLoaderError(
                "Configured trace input path is not a directory: "
                f"{self._trace_directory}"
            )

    def _resolve_source_path(
        self,
        source_path: Path,
    ) -> Path:
        candidate = source_path.expanduser()

        if not candidate.is_absolute():
            candidate = (
                self._trace_directory
                / candidate
            )

        resolved_path = candidate.resolve()

        try:
            resolved_path.relative_to(
                self._trace_directory
            )
        except ValueError as exc:
            raise TraceLoaderError(
                "Trace source must be located inside the configured "
                f"trace directory: {resolved_path}"
            ) from exc

        return resolved_path

    def _validate_source_file(
        self,
        source_path: Path,
    ) -> None:
        if not source_path.exists():
            raise TraceLoaderError(
                f"Trace file was not found: {source_path}"
            )

        if not source_path.is_file():
            raise TraceLoaderError(
                f"Trace source is not a file: {source_path}"
            )

        extension = source_path.suffix.lower()

        if extension not in self._supported_extensions:
            supported = ", ".join(
                sorted(self._supported_extensions)
            )
            raise TraceLoaderError(
                f"Unsupported trace extension '{extension}' "
                f"for {source_path.name}. "
                f"Supported extensions: {supported}"
            )

        try:
            size_bytes = source_path.stat().st_size
        except OSError as exc:
            raise TraceLoaderError(
                f"Cannot read trace metadata: {source_path}"
            ) from exc

        if size_bytes == 0:
            raise TraceLoaderError(
                f"Trace file is empty: {source_path}"
            )

        if size_bytes > self._max_file_size_bytes:
            raise TraceLoaderError(
                f"Trace file exceeds the configured size limit: "
                f"{source_path} "
                f"size_bytes={size_bytes} "
                f"limit_bytes={self._max_file_size_bytes}"
            )

    @staticmethod
    def _calculate_sha256(
        source_path: Path,
    ) -> str:
        digest = hashlib.sha256()

        try:
            with source_path.open("rb") as source_file:
                while block := source_file.read(
                    CHECKSUM_BLOCK_SIZE
                ):
                    digest.update(block)

        except OSError as exc:
            raise TraceLoaderError(
                f"Cannot read trace file: {source_path}"
            ) from exc

        return digest.hexdigest()

    @staticmethod
    def _detect_content_type(
        source_path: Path,
    ) -> str | None:
        content_type, _ = mimetypes.guess_type(
            source_path.name
        )

        return content_type

    @staticmethod
    def _normalize_extension(
        extension: str,
    ) -> str:
        normalized_extension = (
            extension
            .strip()
            .lower()
        )

        if not normalized_extension:
            raise ValueError(
                "Supported trace extension must not be empty"
            )

        if not normalized_extension.startswith("."):
            raise ValueError(
                "Supported trace extension must start with '.'"
            )

        return normalized_extension
