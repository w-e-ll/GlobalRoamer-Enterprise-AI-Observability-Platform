"""Composition root for the application background-worker runtime."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from globalroamer_platform.application.ports.event_publisher import (
    EventPublisher,
)
from globalroamer_platform.bootstrap.outbox import (
    build_outbox_worker,
)
from globalroamer_platform.runtime.application_runtime import (
    ApplicationRuntime,
)
from globalroamer_platform.workers.outbox_worker import (
    OutboxWorkerSettings,
)


def build_application_runtime(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    event_publisher: EventPublisher,
    outbox_settings: OutboxWorkerSettings | None = None,
    shutdown_timeout_seconds: float = 30.0,
) -> ApplicationRuntime:
    """
    Build the managed background-worker runtime.

    The runtime currently manages the transactional outbox publisher.
    Additional workers should be composed and registered here as the
    event-driven processing pipeline grows.
    """
    runtime = ApplicationRuntime(
        shutdown_timeout_seconds=shutdown_timeout_seconds,
    )

    outbox_worker = build_outbox_worker(
        session_factory=session_factory,
        event_publisher=event_publisher,
        settings=outbox_settings,
    )

    runtime.register_worker(
        name="outbox",
        worker=outbox_worker,
    )

    return runtime
