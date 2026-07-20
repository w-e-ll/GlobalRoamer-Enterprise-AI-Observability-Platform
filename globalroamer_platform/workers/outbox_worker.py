"""Runtime worker for publishing transactional outbox messages."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from globalroamer_platform.application.outbox.publish_pending_outbox_messages import (
    PublishPendingOutboxMessages,
    PublishPendingOutboxMessagesCommand,
    PublishPendingOutboxMessagesResult,
)

logger = logging.getLogger(__name__)


AsyncCallback = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class OutboxWorkerSettings:
    """Runtime configuration for the outbox polling worker."""

    poll_interval_seconds: float = 1.0
    batch_size: int = 100
    max_attempts: int = 5
    initial_retry_delay_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.poll_interval_seconds <= 0:
            raise ValueError(
                "poll_interval_seconds must be greater than zero",
            )

        if self.batch_size <= 0:
            raise ValueError(
                "batch_size must be greater than zero",
            )

        if self.max_attempts <= 0:
            raise ValueError(
                "max_attempts must be greater than zero",
            )

        if self.initial_retry_delay_seconds <= 0:
            raise ValueError(
                "initial_retry_delay_seconds must be greater than zero",
            )


class OutboxWorker:
    """Continuously poll and publish pending outbox messages."""

    def __init__(
        self,
        *,
        publisher: PublishPendingOutboxMessages,
        settings: OutboxWorkerSettings | None = None,
        commit: AsyncCallback | None = None,
        rollback: AsyncCallback | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._publisher = publisher
        self._settings = settings or OutboxWorkerSettings()
        self._commit = commit
        self._rollback = rollback
        self._sleep = sleep or asyncio.sleep
        self._stop_event = asyncio.Event()

    async def run_once(
            self,
    ) -> PublishPendingOutboxMessagesResult:
        """Execute one outbox publication batch."""
        command = PublishPendingOutboxMessagesCommand(
            batch_size=self._settings.batch_size,
            max_attempts=self._settings.max_attempts,
            initial_retry_delay_seconds=(
                self._settings.initial_retry_delay_seconds
            ),
        )

        try:
            result = await self._publisher.execute(command)

            if self._commit is not None:
                await self._commit()

        except asyncio.CancelledError:
            if self._rollback is not None:
                await self._rollback()

            logger.info(
                "Outbox worker batch cancelled",
            )
            raise

        except Exception:
            if self._rollback is not None:
                await self._rollback()

            logger.exception(
                "Outbox worker batch failed",
            )
            raise

        logger.info(
            "Outbox worker batch completed "
            "selected_count=%s "
            "published_count=%s "
            "retry_scheduled_count=%s "
            "permanently_failed_count=%s",
            result.selected_count,
            result.published_count,
            result.retry_scheduled_count,
            result.permanently_failed_count,
        )

        return result

    async def run_forever(self) -> None:
        """Run publication batches until stop is requested."""
        logger.info(
            "Outbox worker started "
            "poll_interval_seconds=%s "
            "batch_size=%s "
            "max_attempts=%s",
            self._settings.poll_interval_seconds,
            self._settings.batch_size,
            self._settings.max_attempts,
        )

        self._stop_event.clear()

        try:
            while not self._stop_event.is_set():
                try:
                    result = await self.run_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await self._wait_for_next_poll()
                    continue

                if result.selected_count == 0:
                    await self._wait_for_next_poll()
                    continue

                # Continue immediately while work is available so the worker
                # can drain a backlog without waiting after every batch.
        finally:
            logger.info(
                "Outbox worker stopped",
            )

    def stop(self) -> None:
        """Request graceful worker shutdown."""
        self._stop_event.set()

    @property
    def is_stopping(self) -> bool:
        """Return whether graceful shutdown has been requested."""
        return self._stop_event.is_set()

    async def _wait_for_next_poll(self) -> None:
        """Wait until the next poll or stop request."""
        try:
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=self._settings.poll_interval_seconds,
            )
        except TimeoutError:
            return
