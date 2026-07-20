"""Application service for publishing pending transactional outbox messages."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from globalroamer_platform.application.ports.event_publisher import (
    EventPublisher,
)
from globalroamer_platform.application.ports.outbox_repository import (
    OutboxRepository,
)
from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PublishPendingOutboxMessagesCommand:
    """Configuration for one outbox publication batch."""

    batch_size: int = 100
    max_attempts: int = 5
    initial_retry_delay_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero")

        if self.initial_retry_delay_seconds <= 0:
            raise ValueError(
                "initial_retry_delay_seconds must be greater than zero",
            )


@dataclass(frozen=True, slots=True)
class PublishPendingOutboxMessagesResult:
    """Summary of one outbox publication batch."""

    selected_count: int
    published_count: int
    retry_scheduled_count: int
    permanently_failed_count: int

    @property
    def failed_count(self) -> int:
        """Return the total number of unsuccessful publications."""
        return (
            self.retry_scheduled_count
            + self.permanently_failed_count
        )


class PublishPendingOutboxMessages:
    """Publish pending outbox messages and persist their lifecycle state."""

    def __init__(
        self,
        *,
        repository: OutboxRepository,
        event_publisher: EventPublisher,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._event_publisher = event_publisher
        self._clock = clock or self._utc_now

    async def execute(
        self,
        command: PublishPendingOutboxMessagesCommand,
    ) -> PublishPendingOutboxMessagesResult:
        """Process one batch of currently available outbox messages."""
        batch_started_at = self._clock()

        messages = await self._repository.list_available(
            available_before=batch_started_at,
            limit=command.batch_size,
        )

        published_count = 0
        retry_scheduled_count = 0
        permanently_failed_count = 0

        for message in messages:
            try:
                await self._event_publisher.publish(message.event)
            except Exception as exc:
                failed_message = self._mark_failed(
                    message=message,
                    error=exc,
                    command=command,
                )

                await self._repository.update(failed_message)

                if failed_message.status.value == "failed":
                    permanently_failed_count += 1
                else:
                    retry_scheduled_count += 1

                logger.exception(
                    "Outbox message publication failed "
                    "message_id=%s event_id=%s event_type=%s "
                    "tenant_id=%s correlation_id=%s "
                    "attempt_count=%s status=%s",
                    message.id,
                    message.event_id,
                    message.event_type,
                    message.tenant_id,
                    message.correlation_id,
                    failed_message.attempt_count,
                    failed_message.status.value,
                )

                continue

            published_at = self._clock()

            published_message = (
                message
                .mark_attempted(attempted_at=published_at)
                .mark_published(published_at=published_at)
            )

            await self._repository.update(published_message)

            published_count += 1

            logger.info(
                "Outbox message published "
                "message_id=%s event_id=%s event_type=%s "
                "tenant_id=%s correlation_id=%s attempt_count=%s",
                message.id,
                message.event_id,
                message.event_type,
                message.tenant_id,
                message.correlation_id,
                published_message.attempt_count,
            )

        return PublishPendingOutboxMessagesResult(
            selected_count=len(messages),
            published_count=published_count,
            retry_scheduled_count=retry_scheduled_count,
            permanently_failed_count=permanently_failed_count,
        )

    def _mark_failed(
        self,
        *,
        message: OutboxMessage,
        error: Exception,
        command: PublishPendingOutboxMessagesCommand,
    ) -> OutboxMessage:
        """Create the next lifecycle state after publication failure."""
        failed_at = self._clock()
        next_attempt_count = message.attempt_count + 1
        error_message = self._format_error(error)

        if next_attempt_count >= command.max_attempts:
            return message.mark_failed(
                error=error_message,
                failed_at=failed_at,
            )

        retry_delay = self._calculate_retry_delay(
            attempt_count=next_attempt_count,
            initial_delay_seconds=(
                command.initial_retry_delay_seconds
            ),
        )

        return message.mark_failed(
            error=error_message,
            failed_at=failed_at,
            retry_at=failed_at + retry_delay,
        )

    @staticmethod
    def _calculate_retry_delay(
        *,
        attempt_count: int,
        initial_delay_seconds: float,
    ) -> timedelta:
        """Calculate exponential retry delay without blocking the worker."""
        multiplier = 2 ** (attempt_count - 1)

        return timedelta(
            seconds=initial_delay_seconds * multiplier,
        )

    @staticmethod
    def _format_error(error: Exception) -> str:
        """Return a non-empty error value suitable for persistence."""
        message = str(error).strip()

        if message:
            return message

        return error.__class__.__name__

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)
