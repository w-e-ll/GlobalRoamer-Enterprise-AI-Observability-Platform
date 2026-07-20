from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.application.traces.parse_trace import (
    ParseTrace,
)
from globalroamer_platform.application.traces.process_trace import (
    ProcessTrace,
)
from globalroamer_platform.domain.services.trace_loader import (
    TraceLoader,
)
from globalroamer_platform.infrastructure.persistence.parsed_trace_store import (
    ParsedTraceStore,
)


def build_trace_loader(
    *,
    trace_directory: Path,
    supported_extensions: list[str] | None = None,
    max_file_size_mb: int = 100,
) -> TraceLoader:
    """
    Build the filesystem trace loader.

    The loader validates that source files are located inside the configured
    trace directory, verifies extensions and size limits, and creates
    SourceArtifact metadata.
    """

    return TraceLoader(
        trace_directory=trace_directory,
        supported_extensions=(
            supported_extensions
            if supported_extensions is not None
            else [
                ".csv",
                ".txt",
                ".log",
            ]
        ),
        max_file_size_mb=max_file_size_mb,
    )


def build_process_trace(
    *,
    session: AsyncSession,
    parse_trace: ParseTrace,
    trace_directory: Path,
    supported_extensions: list[str] | None = None,
    max_file_size_mb: int = 100,
) -> ProcessTrace:
    """
    Assemble the complete trace-processing application workflow.

    Workflow:

        source file
            ↓
        TraceLoader
            ↓
        ParseTrace
            ↓
        ParsedTraceStore
            ↓
        PostgreSQL

    The returned ProcessTrace use case does not commit the database
    transaction. Transaction ownership remains with the caller, such as an
    API dependency, worker handler, CLI command, or integration test.
    """

    trace_loader = build_trace_loader(
        trace_directory=trace_directory,
        supported_extensions=supported_extensions,
        max_file_size_mb=max_file_size_mb,
    )

    parsed_trace_store = ParsedTraceStore(
        session=session,
    )

    return ProcessTrace(
        trace_loader=trace_loader,
        parse_trace=parse_trace,
        parsed_trace_store=parsed_trace_store,
    )
