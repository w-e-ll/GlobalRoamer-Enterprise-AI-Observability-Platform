"""Composition root for the application background-worker runtime."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from globalroamer_platform.bootstrap.outbox import (
    build_outbox_worker,
)
from globalroamer_platform.runtime.application_runtime import (
    ApplicationRuntime,
)
from globalroamer_platform.runtime.event_runtime import (
    EventRuntime,
)
from globalroamer_platform.runtime.event_runtime_worker import (
    EventRuntimeWorker,
)
from globalroamer_platform.workers.outbox_worker import (
    OutboxWorkerSettings,
)


def build_application_runtime(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    event_runtime: EventRuntime,
    outbox_settings: OutboxWorkerSettings | None = None,
    shutdown_timeout_seconds: float = 30.0,
) -> ApplicationRuntime:
    """
    Build the managed application background-worker runtime.

    The supplied EventRuntime acts as both:

    - the EventPublisher used by the transactional outbox worker;
    - the in-process dispatcher runtime managed through EventRuntimeWorker.

    The outbox worker is registered before the event-runtime adapter so
    shutdown is requested from the event producer before the event consumer.
    Events may still be queued before EventRuntime starts processing them.
    """
    if not isinstance(
        event_runtime,
        EventRuntime,
    ):
        raise TypeError(
            "event_runtime must be an EventRuntime"
        )

    runtime = ApplicationRuntime(
        shutdown_timeout_seconds=shutdown_timeout_seconds,
    )

    outbox_worker = build_outbox_worker(
        session_factory=session_factory,
        event_publisher=event_runtime,
        settings=outbox_settings,
    )

    event_runtime_worker = EventRuntimeWorker(
        event_runtime=event_runtime,
    )

    runtime.register_worker(
        name="outbox",
        worker=outbox_worker,
    )

    runtime.register_worker(
        name="event-runtime",
        worker=event_runtime_worker,
    )

    return runtime
