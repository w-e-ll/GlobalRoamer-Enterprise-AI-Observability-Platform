"""Managed-worker adapter for the in-process EventRuntime."""

from __future__ import annotations

import asyncio
import logging

from globalroamer_platform.runtime.event_runtime import (
    EventRuntime,
)

logger = logging.getLogger(__name__)


class EventRuntimeWorker:
    """
    Adapt EventRuntime to the ApplicationRuntime ManagedWorker protocol.

    EventRuntime keeps its native lifecycle and deterministic
    ``process_until_idle()`` testing API. This adapter only translates that
    lifecycle into ``run_forever()`` and synchronous ``stop()`` methods.
    """

    def __init__(
        self,
        *,
        event_runtime: EventRuntime,
    ) -> None:
        if not isinstance(
            event_runtime,
            EventRuntime,
        ):
            raise TypeError(
                "event_runtime must be an EventRuntime"
            )

        self._event_runtime = event_runtime
        self._stop_requested = asyncio.Event()

    async def run_forever(self) -> None:
        """
        Start EventRuntime and wait until graceful shutdown is requested.
        """
        self._stop_requested.clear()

        await self._event_runtime.start()

        logger.info("Event runtime worker started")

        try:
            await self._stop_requested.wait()
        except asyncio.CancelledError:
            logger.info("Event runtime worker cancelled")
            raise
        finally:
            await self._event_runtime.stop()

        logger.info("Event runtime worker stopped")

    def stop(self) -> None:
        """Request graceful shutdown."""
        self._stop_requested.set()
