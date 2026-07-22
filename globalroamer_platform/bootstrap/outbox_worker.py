"""Composition root for the transactional outbox worker."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from globalroamer_platform.application.outbox.publish_pending_outbox_messages import (
    PublishPendingOutboxMessages,
)
from globalroamer_platform.application.ports.event_publisher import (
    EventPublisher,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
)
from globalroamer_platform.runtime.session_scoped_outbox_publisher import (
    SessionScopedOutboxPublisher,
)
from globalroamer_platform.workers.outbox_worker import (
    OutboxWorker,
    OutboxWorkerSettings,
)


class EventPublisherFactory(Protocol):
    """Create the event transport used by the outbox publisher."""

    def __call__(self) -> EventPublisher:
        """Return an event publisher instance."""
        ...


def build_outbox_worker(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    event_publisher: EventPublisher,
    settings: OutboxWorkerSettings | None = None,
) -> OutboxWorker:
    """
    Build the production transactional outbox worker.

    A fresh SQLAlchemy session, repository, and application service are
    created for every polling iteration. The supplied EventPublisher is
    expected to be thread-safe (or coroutine-safe) and long-lived.
    """

    def build_publisher(
        session: AsyncSession,
    ) -> PublishPendingOutboxMessages:
        repository = SQLAlchemyOutboxRepository(
            session=session,
        )

        return PublishPendingOutboxMessages(
            repository=repository,
            event_publisher=event_publisher,
        )

    publisher = SessionScopedOutboxPublisher(
        session_factory=session_factory,
        publisher_factory=build_publisher,
    )

    return OutboxWorker(
        publisher=publisher,
        settings=settings,
    )


def build_outbox_worker_with_publisher_factory(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    event_publisher_factory: EventPublisherFactory,
    settings: OutboxWorkerSettings | None = None,
) -> OutboxWorker:
    """
    Build an OutboxWorker that creates a new EventPublisher for every
    publication batch.

    This variant is intended for transports that are intentionally
    short-lived. Most broker clients should instead be created once and
    supplied to build_outbox_worker().
    """

    def build_publisher(
        session: AsyncSession,
    ) -> PublishPendingOutboxMessages:
        repository = SQLAlchemyOutboxRepository(
            session=session,
        )

        return PublishPendingOutboxMessages(
            repository=repository,
            event_publisher=event_publisher_factory(),
        )

    publisher = SessionScopedOutboxPublisher(
        session_factory=session_factory,
        publisher_factory=build_publisher,
    )

    return OutboxWorker(
        publisher=publisher,
        settings=settings,
    )
