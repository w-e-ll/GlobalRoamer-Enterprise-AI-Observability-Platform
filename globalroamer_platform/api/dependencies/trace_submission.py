"""Dependency providers for asynchronous trace submission."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.api.dependencies.database import (
    get_database_session,
)
from globalroamer_platform.application.traces.submit_trace import (
    SubmitTrace,
)
from globalroamer_platform.bootstrap.trace_submission import (
    build_submit_trace,
)
from globalroamer_platform.core.config import (
    get_platform_config,
)


DatabaseSessionDependency = Annotated[
    AsyncSession,
    Depends(get_database_session),
]


def get_submit_trace(
    session: DatabaseSessionDependency,
) -> SubmitTrace:
    """Build the request-scoped trace-submission use case."""

    platform_config = get_platform_config()

    return build_submit_trace(
        session=session,
        artifact_storage_directory=(
            platform_config.paths.artifact_storage_dir
        ),
    )
