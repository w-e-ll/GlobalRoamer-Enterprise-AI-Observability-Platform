"""Dependency providers for asynchronous trace submission."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.api.dependencies.database import get_database_session
from globalroamer_platform.application.traces.submit_trace import SubmitTrace
from globalroamer_platform.bootstrap.trace_submission import build_submit_trace


DatabaseSessionDependency = Annotated[
    AsyncSession,
    Depends(get_database_session),
]


def get_submit_trace(session: DatabaseSessionDependency) -> SubmitTrace:
    return build_submit_trace(session=session)
