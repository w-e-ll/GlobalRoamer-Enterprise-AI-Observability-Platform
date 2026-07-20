"""Executable entry point for the transactional outbox worker."""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Callable

from globalroamer_platform.bootstrap.outbox_worker import (
    build_outbox_worker,
)
from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)
from globalroamer_platform.infrastructure.messaging.in_memory_event_publisher import (
    InMemoryEventPublisher,
)
from globalroamer_platform.workers.outbox_worker import (
    OutboxWorker,
    OutboxWorkerSettings,
)

logger = logging.getLogger(__name__)


def _request_shutdown(
    *,
    worker: OutboxWorker,
    signal_name: str,
) -> None:
    """Request graceful shutdown after receiving an OS signal."""
    logger.info(
        "Outbox worker shutdown requested signal=%s",
        signal_name,
    )
    worker.stop()


def _register_signal_handlers(
    *,
    loop: asyncio.AbstractEventLoop,
    worker: OutboxWorker,
) -> None:
    """Register graceful shutdown handlers where supported."""
    for shutdown_signal in (
        signal.SIGINT,
        signal.SIGTERM,
    ):
        callback: Callable[[], None] = (
            lambda current_signal=shutdown_signal: _request_shutdown(
                worker=worker,
                signal_name=current_signal.name,
            )
        )

        try:
            loop.add_signal_handler(
                shutdown_signal,
                callback,
            )
        except NotImplementedError:
            logger.warning(
                "Signal handlers are not supported "
                "signal=%s",
                shutdown_signal.name,
            )


async def run() -> None:
    """Build and run the transactional outbox worker."""
    logger.info(
        "Starting transactional outbox worker runtime",
    )

    event_publisher = InMemoryEventPublisher()

    settings = OutboxWorkerSettings(
        poll_interval_seconds=1.0,
        batch_size=100,
        max_attempts=5,
        initial_retry_delay_seconds=5.0,
    )

    async with async_session_factory() as session:
        worker = build_outbox_worker(
            session=session,
            event_publisher=event_publisher,
            settings=settings,
        )

        loop = asyncio.get_running_loop()

        _register_signal_handlers(
            loop=loop,
            worker=worker,
        )

        try:
            await worker.run_forever()
        except asyncio.CancelledError:
            logger.info(
                "Outbox worker runtime cancelled",
            )
            raise
        finally:
            worker.stop()

            logger.info(
                "Transactional outbox worker runtime stopped",
            )


def main() -> None:
    """Run the worker process."""
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info(
            "Outbox worker interrupted",
        )


if __name__ == "__main__":
    main()
