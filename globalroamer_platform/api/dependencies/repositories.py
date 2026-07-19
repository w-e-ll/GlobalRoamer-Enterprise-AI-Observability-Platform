from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.api.dependencies.database import (
    get_database_session,
)
from globalroamer_platform.application.ports.trace_repository import (
    TraceRepository,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_trace_repository import (
    SQLAlchemyTraceRepository,
)


DatabaseSessionDependency = Annotated[
    AsyncSession,
    Depends(get_database_session),
]


def get_trace_repository(
    session: DatabaseSessionDependency,
) -> TraceRepository:
    """Create a trace repository bound to the current database session."""

    return SQLAlchemyTraceRepository(session)
