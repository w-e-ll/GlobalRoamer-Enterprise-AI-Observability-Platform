"""Bootstrap wiring for asynchronous trace submission."""

from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.application.traces.submit_trace import SubmitTrace
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
)


def build_submit_trace(*, session: AsyncSession) -> SubmitTrace:
    return SubmitTrace(
        outbox_repository=SQLAlchemyOutboxRepository(session=session),
    )
