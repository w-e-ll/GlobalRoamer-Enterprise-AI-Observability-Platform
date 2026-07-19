# globalroamer_platform/infrastructure/database/session.py

import logging
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from globalroamer_platform.core.config import get_settings


logger = logging.getLogger(__name__)


settings = get_settings()

logger.info(
    "Creating asynchronous database engine"
)

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=False,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_database_session() -> AsyncIterator[AsyncSession]:
    """Provide a request-scoped asynchronous database session."""

    logger.debug(
        "Opening database session"
    )

    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            logger.exception(
                "Database session failed; rolling back transaction"
            )

            await session.rollback()
            raise
        finally:
            logger.debug(
                "Closing database session"
            )
