# globalroamer_platform/infrastructure/database/health.py

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)


async def check_database_health() -> bool:
    """
    Check whether the database is reachable.

    Returns:
        True if PostgreSQL responds successfully.
        False otherwise.
    """

    try:
        async with async_session_factory() as session:
            await session.execute(
                text("SELECT 1"),
            )

        return True

    except SQLAlchemyError:
        return False
