"""Bootstrap wiring for the parser worker."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.bootstrap.process_artifact import (
    build_process_artifact,
)
from globalroamer_platform.bootstrap.trace_parsing import (
    TraceParsingSettings,
    build_parse_trace,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
)
from globalroamer_platform.workers.parser_worker import (
    ParserWorker,
)


def build_parser_worker(
    *,
    session: AsyncSession,
    trace_directory: Path,
    mapping_configuration_path: Path,
    artifact_storage_directory: Path | None = None,
    source_timezone: str = "UTC",
    target_timezone: str = "UTC",
    supported_extensions: list[str] | None = None,
    max_file_size_mb: int = 100,
) -> ParserWorker:
    """
    Build the complete parser-worker dependency graph.

    The preferred source root is artifact_storage_directory. The existing
    trace_directory parameter remains as a temporary compatibility fallback
    for older callers and tests.

    The same AsyncSession is shared by:

    - SQLAlchemyArtifactRepository
    - ParsedTraceStore
    - SQLAlchemyOutboxRepository

    This allows artifact status updates, parsed-trace persistence, and the
    outgoing TRACE_PARSED event to be committed atomically by the outer
    runtime transaction.
    """

    storage_directory = (
        artifact_storage_directory
        if artifact_storage_directory
        is not None
        else trace_directory
    )

    parsing_settings = TraceParsingSettings(
        mapping_configuration_path=(
            mapping_configuration_path
        ),
        source_timezone=source_timezone,
        target_timezone=target_timezone,
    )

    parse_trace = build_parse_trace(
        settings=parsing_settings,
    )

    process_artifact = build_process_artifact(
        session=session,
        parse_trace=parse_trace,
        artifact_storage_directory=(
            storage_directory
        ),
        supported_extensions=(
            supported_extensions
        ),
        max_file_size_mb=max_file_size_mb,
    )

    outbox_repository = (
        SQLAlchemyOutboxRepository(
            session=session,
        )
    )

    return ParserWorker(
        process_artifact=process_artifact,
        outbox_repository=outbox_repository,
    )
