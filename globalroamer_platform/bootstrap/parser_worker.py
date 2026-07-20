"""Bootstrap wiring for the parser worker."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.bootstrap.trace_parsing import (
    TraceParsingSettings,
    build_parse_trace,
)
from globalroamer_platform.bootstrap.trace_processing import (
    build_process_trace,
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
    source_timezone: str = "UTC",
    target_timezone: str = "UTC",
    supported_extensions: list[str] | None = None,
    max_file_size_mb: int = 100,
) -> ParserWorker:
    """
    Build the complete parser worker dependency graph.

    The same AsyncSession is shared by:

    - ParsedTraceStore
    - SQLAlchemyOutboxRepository

    This allows the parsed trace and outgoing outbox message to be committed
    atomically by the outer runtime transaction.
    """

    parsing_settings = TraceParsingSettings(
        mapping_configuration_path=mapping_configuration_path,
        source_timezone=source_timezone,
        target_timezone=target_timezone,
    )

    parse_trace = build_parse_trace(
        settings=parsing_settings,
    )

    process_trace = build_process_trace(
        session=session,
        parse_trace=parse_trace,
        trace_directory=trace_directory,
        supported_extensions=supported_extensions,
        max_file_size_mb=max_file_size_mb,
    )

    outbox_repository = SQLAlchemyOutboxRepository(
        session=session,
    )

    return ParserWorker(
        process_trace=process_trace,
        outbox_repository=outbox_repository,
    )
