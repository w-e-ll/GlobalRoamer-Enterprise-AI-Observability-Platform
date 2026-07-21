"""Session-scoped runtime adapter for transactional outbox publication."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from globalroamer_platform.application.outbox.publish_pending_outbox_messages import (
    PublishPendingOutboxMessages,
    PublishPendingOutboxMessagesCommand,
    PublishPendingOutboxMessagesResult,
)

logger = logging.getLogger(__name__)


class OutboxPublisherFactory(Protocol):
    """Build an outbox publication application service for one DB session."""

    def __call__(
        self,
        session: AsyncSession,
    ) -> PublishPendingOutboxMessages:
        """Create the application service bound to the supplied session."""
        ...


class SessionScopedOutboxPublisher:
    """
    Execute each outbox publication batch in a fresh database session.

    The adapter keeps SQLAlchemy lifecycle concerns outside OutboxWorker and
    outside the application service. A session is opened for one execute call,
    committed only after successful publication-state updates, rolled back on
    failure or cancellation, and then closed by the session context manager.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        publisher_factory: OutboxPublisherFactory,
    ) -> None:
        self._session_factory = session_factory
        self._publisher_factory = publisher_factory

    async def execute(
        self,
        command: PublishPendingOutboxMessagesCommand,
    ) -> PublishPendingOutboxMessagesResult:
        """Publish one transactional outbox batch in an isolated session."""
        logger.debug(
            "Opening session-scoped outbox publication batch "
            "batch_size=%s max_attempts=%s",
            command.batch_size,
            command.max_attempts,
        )

        async with self._session_factory() as session:
            publisher = self._publisher_factory(session)

            try:
                result = await publisher.execute(command)
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
                    "Session-scoped outbox publication batch failed "
                    "batch_size=%s max_attempts=%s",
                    command.batch_size,
                    command.max_attempts,
                )
                raise

        logger.debug(
            "Session-scoped outbox publication batch committed "
            "selected_count=%s published_count=%s "
            "retry_scheduled_count=%s permanently_failed_count=%s",
            result.selected_count,
            result.published_count,
            result.retry_scheduled_count,
            result.permanently_failed_count,
        )

        return result

    @staticmethod
    async def _rollback_safely(
        *,
        session: AsyncSession,
        reason: str,
    ) -> None:
        """
        Roll back the current transaction without masking the original error.

        Rollback failures are logged because the original publication or
        cancellation exception remains the primary failure signal.
        """
        try:
            await session.rollback()
        except Exception:
            logger.exception(
                "Outbox publication session rollback failed reason=%s",
                reason,
            )
