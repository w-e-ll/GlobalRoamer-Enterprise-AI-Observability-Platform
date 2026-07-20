"""Domain entity representing a durable transactional outbox message."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from globalroamer_platform.domain.events.event_envelope import EventEnvelope


class OutboxMessageStatus(StrEnum):
    """Lifecycle states of an outbox message."""

    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    """A durable event waiting to be published.

    The entity contains the event envelope and the state required by an
    outbox polling process.

    The domain entity is immutable. Lifecycle methods return updated copies
    rather than modifying the existing object.
    """

    id: UUID
    event: EventEnvelope
    status: OutboxMessageStatus
    attempt_count: int
    created_at: datetime
    available_at: datetime
    published_at: datetime | None
    last_attempt_at: datetime | None
    last_error: str | None

    @classmethod
    def create(
        cls,
        *,
        event: EventEnvelope,
        available_at: datetime | None = None,
    ) -> OutboxMessage:
        """Create a pending outbox message for an event."""
        now = datetime.now(timezone.utc)

        return cls(
            id=uuid4(),
            event=event,
            status=OutboxMessageStatus.PENDING,
            attempt_count=0,
            created_at=now,
            available_at=available_at or now,
            published_at=None,
            last_attempt_at=None,
            last_error=None,
        )

    @property
    def event_id(self) -> UUID:
        """Return the contained event identifier."""
        return self.event.event_id

    @property
    def event_type(self) -> str:
        """Return the contained event type."""
        return self.event.event_type

    @property
    def tenant_id(self) -> str:
        """Return the contained event tenant."""
        return self.event.tenant_id

    @property
    def correlation_id(self) -> str:
        """Return the contained event correlation identifier."""
        return self.event.correlation_id

    @property
    def payload(self) -> dict[str, Any]:
        """Return the contained event payload."""
        return self.event.payload

    def is_available(
        self,
        *,
        at: datetime | None = None,
    ) -> bool:
        """Return whether this message is ready for publication."""
        reference_time = at or datetime.now(timezone.utc)

        return (
            self.status == OutboxMessageStatus.PENDING
            and self.available_at <= reference_time
        )

    def mark_attempted(
        self,
        *,
        attempted_at: datetime | None = None,
    ) -> OutboxMessage:
        """Record one publication attempt."""
        timestamp = attempted_at or datetime.now(timezone.utc)

        return replace(
            self,
            attempt_count=self.attempt_count + 1,
            last_attempt_at=timestamp,
        )

    def mark_published(
        self,
        *,
        published_at: datetime | None = None,
    ) -> OutboxMessage:
        """Mark the message as successfully published."""
        timestamp = published_at or datetime.now(timezone.utc)

        return replace(
            self,
            status=OutboxMessageStatus.PUBLISHED,
            published_at=timestamp,
            last_attempt_at=timestamp,
            last_error=None,
        )

    def mark_failed(
        self,
        *,
        error: str,
        retry_at: datetime | None = None,
        failed_at: datetime | None = None,
    ) -> OutboxMessage:
        """Record a failed publication attempt.

        When ``retry_at`` is supplied, the message remains pending and becomes
        available again at that time. Without ``retry_at``, it is marked as
        permanently failed.
        """
        normalized_error = error.strip()

        if not normalized_error:
            raise ValueError("error must not be empty")

        timestamp = failed_at or datetime.now(timezone.utc)

        if retry_at is not None:
            return replace(
                self,
                status=OutboxMessageStatus.PENDING,
                attempt_count=self.attempt_count + 1,
                available_at=retry_at,
                last_attempt_at=timestamp,
                last_error=normalized_error,
            )

        return replace(
            self,
            status=OutboxMessageStatus.FAILED,
            attempt_count=self.attempt_count + 1,
            last_attempt_at=timestamp,
            last_error=normalized_error,
        )
