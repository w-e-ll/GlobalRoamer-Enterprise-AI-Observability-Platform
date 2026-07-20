"""Application port for transactional outbox persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from globalroamer_platform.domain.entities.outbox_message import OutboxMessage


class OutboxRepository(Protocol):
    """Persistence contract for durable outbox messages."""

    async def add(
        self,
        message: OutboxMessage,
    ) -> None:
        """Persist a newly created outbox message."""
        ...

    async def get_by_id(
        self,
        message_id: UUID,
    ) -> OutboxMessage | None:
        """Return an outbox message by its identifier."""
        ...

    async def get_by_event_id(
        self,
        event_id: UUID,
    ) -> OutboxMessage | None:
        """Return an outbox message by the contained event identifier."""
        ...

    async def list_available(
        self,
        *,
        available_before: datetime,
        limit: int = 100,
    ) -> list[OutboxMessage]:
        """Return pending messages ready for publication.

        Implementations should return messages ordered by availability time
        and creation time to preserve deterministic processing.
        """
        ...

    async def update(
        self,
        message: OutboxMessage,
    ) -> None:
        """Persist the current lifecycle state of an outbox message."""
        ...
