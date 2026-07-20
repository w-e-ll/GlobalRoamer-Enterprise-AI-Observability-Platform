"""Dependency assembly for the transactional outbox worker."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.application.outbox.publish_pending_outbox_messages import (
    PublishPendingOutboxMessages,
)
from globalroamer_platform.application.ports.event_publisher import (
    EventPublisher,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
)
from globalroamer_platform.workers.outbox_worker import (
    OutboxWorker,
    OutboxWorkerSettings,
)


def build_outbox_worker(
    *,
    session: AsyncSession,
    event_publisher: EventPublisher,
    settings: OutboxWorkerSettings | None = None,
) -> OutboxWorker:
    """Build a fully configured transactional outbox worker.

    The supplied SQLAlchemy session represents the worker transaction
    boundary. The worker commits after a successful batch and rolls back after
    an unexpected failure or cancellation.

    Args:
        session: Long-lived asynchronous database session owned by the worker
            runtime.
        event_publisher: Concrete transport used to publish event envelopes.
        settings: Optional worker polling, batching, and retry configuration.

    Returns:
        A fully assembled OutboxWorker instance.
    """
    repository = SQLAlchemyOutboxRepository(
        session=session,
    )

    publish_pending_messages = PublishPendingOutboxMessages(
        repository=repository,
        event_publisher=event_publisher,
    )

    return OutboxWorker(
        publisher=publish_pending_messages,
        settings=settings,
        commit=session.commit,
        rollback=session.rollback,
    )
