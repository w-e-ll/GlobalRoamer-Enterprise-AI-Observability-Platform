"""Application runtime lifecycle for managed background workers."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


class ManagedWorker(Protocol):
    """Background worker managed by the application runtime."""

    async def run_forever(self) -> None:
        """Run until graceful stop or task cancellation."""
        ...

    def stop(self) -> None:
        """Request graceful shutdown."""
        ...


@dataclass(slots=True)
class ManagedWorkerTask:
    """Runtime state for one managed worker."""

    name: str
    worker: ManagedWorker
    task: asyncio.Task[None] | None = field(
        default=None,
        init=False,
        repr=False,
    )


class ApplicationRuntime:
    """Start, supervise, and stop application background workers."""

    def __init__(
        self,
        *,
        shutdown_timeout_seconds: float = 30.0,
    ) -> None:
        if shutdown_timeout_seconds <= 0:
            raise ValueError(
                "shutdown_timeout_seconds must be greater than zero"
            )

        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._workers: list[ManagedWorkerTask] = []
        self._started = False
        self._stopping = False

    def register_worker(
        self,
        *,
        name: str,
        worker: ManagedWorker,
    ) -> None:
        """Register a worker before runtime startup."""
        normalized_name = name.strip()

        if not normalized_name:
            raise ValueError("worker name must not be empty")

        if self._started:
            raise RuntimeError(
                "workers cannot be registered after runtime startup"
            )

        if any(item.name == normalized_name for item in self._workers):
            raise ValueError(
                f"worker is already registered: {normalized_name}"
            )

        self._workers.append(
            ManagedWorkerTask(
                name=normalized_name,
                worker=worker,
            )
        )

    async def start(self) -> None:
        """Start all registered workers."""
        if self._started:
            raise RuntimeError("application runtime is already started")

        self._started = True
        self._stopping = False

        logger.info(
            "Application runtime starting worker_count=%s",
            len(self._workers),
        )

        for managed in self._workers:
            managed.task = asyncio.create_task(
                self._run_worker(managed),
                name=f"globalroamer:{managed.name}",
            )

            logger.info(
                "Background worker task started worker_name=%s",
                managed.name,
            )

        logger.info(
            "Application runtime started worker_count=%s",
            len(self._workers),
        )

    async def stop(self) -> None:
        """Gracefully stop all workers and cancel overdue tasks."""
        if not self._started:
            return

        if self._stopping:
            return

        self._stopping = True

        logger.info(
            "Application runtime stopping worker_count=%s "
            "shutdown_timeout_seconds=%s",
            len(self._workers),
            self._shutdown_timeout_seconds,
        )

        for managed in self._workers:
            try:
                managed.worker.stop()
            except Exception:
                logger.exception(
                    "Background worker stop request failed "
                    "worker_name=%s",
                    managed.name,
                )

        tasks = [
            managed.task
            for managed in self._workers
            if managed.task is not None
        ]

        if tasks:
            done, pending = await asyncio.wait(
                tasks,
                timeout=self._shutdown_timeout_seconds,
            )

            for task in pending:
                logger.warning(
                    "Background worker exceeded shutdown timeout "
                    "task_name=%s",
                    task.get_name(),
                )
                task.cancel()

            if pending:
                await asyncio.gather(
                    *pending,
                    return_exceptions=True,
                )

            for task in done:
                self._log_task_result(task)

        self._started = False
        self._stopping = False

        for managed in self._workers:
            managed.task = None

        logger.info("Application runtime stopped")

    async def _run_worker(
        self,
        managed: ManagedWorkerTask,
    ) -> None:
        """Run one worker and preserve failure visibility."""
        try:
            await managed.worker.run_forever()
        except asyncio.CancelledError:
            logger.info(
                "Background worker task cancelled worker_name=%s",
                managed.name,
            )
            raise
        except Exception:
            logger.exception(
                "Background worker terminated unexpectedly "
                "worker_name=%s",
                managed.name,
            )
            raise
        else:
            logger.info(
                "Background worker task completed worker_name=%s",
                managed.name,
            )

    @staticmethod
    def _log_task_result(
        task: asyncio.Task[None],
    ) -> None:
        """Observe completed task exceptions during shutdown."""
        if task.cancelled():
            return

        exception = task.exception()

        if exception is not None:
            logger.error(
                "Background worker task finished with error "
                "task_name=%s error_type=%s",
                task.get_name(),
                type(exception).__name__,
                exc_info=(
                    type(exception),
                    exception,
                    exception.__traceback__,
                ),
            )

    @property
    def is_started(self) -> bool:
        """Return whether the runtime is active."""
        return self._started

    @property
    def is_stopping(self) -> bool:
        """Return whether shutdown is in progress."""
        return self._stopping
