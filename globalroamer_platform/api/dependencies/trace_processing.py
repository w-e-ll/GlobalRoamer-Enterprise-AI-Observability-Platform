"""Dependency providers for the trace-processing API."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.api.dependencies.database import (
    get_database_session,
)
from globalroamer_platform.application.traces.process_trace import (
    ProcessTrace,
)
from globalroamer_platform.bootstrap.trace_parsing import (
    TraceParsingSettings,
    build_trace_parsing_container,
    validate_trace_parsing_configuration,
)
from globalroamer_platform.bootstrap.trace_processing import (
    build_process_trace,
)


DatabaseSessionDependency = Annotated[
    AsyncSession,
    Depends(get_database_session),
]


TRACE_DIRECTORY = Path("etc")
MAPPING_CONFIGURATION_PATH = Path("etc/trace_mapping.yml")


def get_process_trace(
    session: DatabaseSessionDependency,
) -> ProcessTrace:
    """Provide a request-scoped ProcessTrace application service.

    Args:
        session: Request-scoped asynchronous database session.

    Returns:
        Fully configured trace-processing application service.
    """
    parsing_settings = TraceParsingSettings(
        mapping_configuration_path=MAPPING_CONFIGURATION_PATH,
        source_timezone="UTC",
        target_timezone="UTC",
    )

    parsing_container = build_trace_parsing_container(
        settings=parsing_settings,
    )

    validate_trace_parsing_configuration(
        parsing_container,
    )

    return build_process_trace(
        session=session,
        parse_trace=parsing_container.parse_trace,
        trace_directory=TRACE_DIRECTORY,
        supported_extensions=[
            ".csv",
            ".txt",
            ".log",
        ],
        max_file_size_mb=100,
    )
