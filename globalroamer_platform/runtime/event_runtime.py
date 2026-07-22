"""In-process runtime for asynchronous integration-event dispatching."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.runtime.event_dispatcher import (
    EventDispatcher,
)

logger = logging.getLogger(__name__)


class EventRuntime:
    """
    Drive integration events through the in-process event dispatcher.

    Published events are placed onto an internal FIFO queue. Each event is
    dispatched to its registered handlers. Follow-up events returned by those
    handlers are appended to the same queue and processed in order.

    The runtime can operate in two modes:

    - ``start()`` and ``stop()`` for normal background execution;
    - ``process_until_idle()`` for deterministic tests and one-shot processing.

    This class implements the EventPublisher contract through ``publish()``.
    """

    _STOP = object()

    def __init__(
        self,
        *,
        dispatcher: EventDispatcher,
    ) -> None:
        self._dispatcher = dispatcher
        self._queue: asyncio.Queue[EventEnvelope | object] = (
            asyncio.Queue()
        )
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    @property
    def is_running(self) -> bool:
        """Return whether the background event loop is currently running."""
        return self._task is not None and not self._task.done()

    @property
    def pending_event_count(self) -> int:
        """Return the number of queued items awaiting processing."""
        return self._queue.qsize()

    async def publish(
        self,
        event: EventEnvelope,
    ) -> None:
        """Publish an event to the internal processing queue."""
        if self._stopping:
            raise RuntimeError(
                "Cannot publish events while the event runtime is stopping"
            )

        await self._queue.put(event)

        logger.debug(
            "Integration event queued "
            "event_type=%s event_id=%s pending_count=%s",
            event.event_type,
            event.event_id,
            self._queue.qsize(),
        )

    async def start(self) -> None:
        """Start the background event-processing loop."""
        if self.is_running:
            logger.debug("Event runtime is already running")
            return

        self._stopping = False
        self._task = asyncio.create_task(
            self._run(),
            name="globalroamer-event-runtime",
        )

        logger.info("Event runtime started")

    async def stop(self) -> None:
        """
        Stop the background event-processing loop.

        Events already ahead of the stop marker remain ordered and are handled
        before the runtime exits. Events cannot be published once shutdown has
        started.
        """
        if self._task is None:
            return

        if self._task.done():
            await self._finalize_completed_task()
            return

        self._stopping = True
        await self._queue.put(self._STOP)

        try:
            await self._task
        finally:
            self._task = None
            self._stopping = False

        logger.info("Event runtime stopped")

    async def process_until_idle(self) -> int:
        """
        Process queued events until no events remain.

        Follow-up events produced during dispatch are also processed. The
        returned count represents the total number of dispatched events.
        """
        processed_count = 0

        while not self._queue.empty():
            item = await self._queue.get()

            try:
                if item is self._STOP:
                    continue

                event = self._require_event(item)
                await self._dispatch_and_enqueue_follow_up_events(event)
                processed_count += 1
            finally:
                self._queue.task_done()

        return processed_count

    async def _run(self) -> None:
        """Continuously process queued events until the stop marker arrives."""
        try:
            while True:
                item = await self._queue.get()

                try:
                    if item is self._STOP:
                        return

                    event = self._require_event(item)
                    await self._dispatch_and_enqueue_follow_up_events(event)

                except asyncio.CancelledError:
                    logger.info("Event runtime processing cancelled")
                    raise

                except Exception:
                    logger.exception(
                        "Event runtime failed while dispatching event"
                    )
                    raise

                finally:
                    self._queue.task_done()

        finally:
            logger.debug("Event runtime processing loop exited")

    async def _dispatch_and_enqueue_follow_up_events(
        self,
        event: EventEnvelope,
    ) -> None:
        logger.debug(
            "Dispatching integration event "
            "event_type=%s event_id=%s",
            event.event_type,
            event.event_id,
        )

        produced_events = await self._dispatcher.dispatch(event)

        await self._enqueue_all(produced_events)

        logger.debug(
            "Integration event dispatched "
            "event_type=%s event_id=%s produced_count=%s",
            event.event_type,
            event.event_id,
            len(produced_events),
        )

    async def _enqueue_all(
        self,
        events: Iterable[EventEnvelope],
    ) -> None:
        for event in events:
            await self._queue.put(event)

    async def _finalize_completed_task(self) -> None:
        task = self._task
        self._task = None
        self._stopping = False

        if task is not None:
            await task

    @staticmethod
    def _require_event(
        item: EventEnvelope | object,
    ) -> EventEnvelope:
        if not isinstance(item, EventEnvelope):
            raise TypeError(
                "Event runtime queue contained an unsupported item"
            )

        return item
