from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)


async def get_database_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()