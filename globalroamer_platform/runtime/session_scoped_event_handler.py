"""Session-scoped runtime adapter for transactional event handling."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)

logger = logging.getLogger(__name__)


class EventHandlerFactory(Protocol):
    """Build an event handler bound to one database session."""

    def __call__(
        self,
        session: AsyncSession,
    ) -> "EventHandler":
        ...


class EventHandler(Protocol):
    """Application event handler."""

    async def handle(
        self,
        event: EventEnvelope,
    ) -> EventEnvelope | None:
        """
        Handle one event.

        Returns a follow-up event when one is produced.
        """
        ...


class SessionScopedEventHandler:
    """
    Execute one event handler in a fresh database session.

    A new SQLAlchemy session is opened for every dispatched event.
    Successful handling commits the transaction. Failures or task
    cancellation trigger rollback before the exception is re-raised.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        handler_factory: EventHandlerFactory,
    ) -> None:
        self._session_factory = session_factory
        self._handler_factory = handler_factory

    async def handle(
        self,
        event: EventEnvelope,
    ) -> EventEnvelope | None:
        """Handle one event inside an isolated transaction."""
        logger.debug(
            "Opening session-scoped event handler "
            "event_type=%s event_id=%s",
            event.event_type,
            event.event_id,
        )

        async with self._session_factory() as session:
            handler = self._handler_factory(session)

            try:
                result = await handler.handle(event)
                await session.commit()

            except asyncio.CancelledError:
                await self._rollback_safely(
                    session=session,
                    reason="cancelled",
                )
                raise

            except Exception:
                await self._rollback_safely(
                    session=session,
                    reason="failed",
                )

                logger.exception(
                    "Session-scoped event handler failed "
                    "event_type=%s event_id=%s",
                    event.event_type,
                    event.event_id,
                )
                raise

        logger.debug(
            "Session-scoped event handler committed "
            "event_type=%s event_id=%s",
            event.event_type,
            event.event_id,
        )

        return result

    @staticmethod
    async def _rollback_safely(
        *,
        session: AsyncSession,
        reason: str,
    ) -> None:
        """Rollback without masking the original exception."""
        try:
            await session.rollback()
        except Exception:
            logger.exception(
                "Event handler session rollback failed "
                "reason=%s",
                reason,
            )
