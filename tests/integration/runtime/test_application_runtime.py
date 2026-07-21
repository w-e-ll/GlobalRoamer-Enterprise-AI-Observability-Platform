"""Integration tests for the managed application worker runtime."""

from __future__ import annotations

import asyncio

import pytest

from globalroamer_platform.runtime.application_runtime import (
    ApplicationRuntime,
)


class GracefulWorker:
    """Worker that exits after receiving a graceful stop request."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.stop_requested = asyncio.Event()
        self.finished = asyncio.Event()
        self.run_count = 0
        self.stop_count = 0

    async def run_forever(self) -> None:
        self.run_count += 1
        self.started.set()

        try:
            await self.stop_requested.wait()
        finally:
            self.finished.set()

    def stop(self) -> None:
        self.stop_count += 1
        self.stop_requested.set()


class CancellationOnlyWorker:
    """Worker that ignores graceful stop and exits only on cancellation."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.stop_count = 0

    async def run_forever(self) -> None:
        self.started.set()

        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise

    def stop(self) -> None:
        self.stop_count += 1


class FailingWorker:
    """Worker that fails after it has started."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.stop_count = 0

    async def run_forever(self) -> None:
        self.started.set()
        raise RuntimeError("worker failure")

    def stop(self) -> None:
        self.stop_count += 1


@pytest.mark.asyncio
async def test_runtime_starts_and_stops_worker_gracefully() -> None:
    worker = GracefulWorker()
    runtime = ApplicationRuntime(
        shutdown_timeout_seconds=1.0,
    )
    runtime.register_worker(
        name="graceful-worker",
        worker=worker,
    )

    await runtime.start()
    await asyncio.wait_for(worker.started.wait(), timeout=1.0)

    assert runtime.is_started is True
    assert runtime.is_stopping is False
    assert worker.run_count == 1

    await runtime.stop()

    assert runtime.is_started is False
    assert runtime.is_stopping is False
    assert worker.stop_count == 1
    assert worker.finished.is_set()


@pytest.mark.asyncio
async def test_runtime_stop_is_idempotent() -> None:
    worker = GracefulWorker()
    runtime = ApplicationRuntime(
        shutdown_timeout_seconds=1.0,
    )
    runtime.register_worker(
        name="graceful-worker",
        worker=worker,
    )

    await runtime.start()
    await asyncio.wait_for(worker.started.wait(), timeout=1.0)

    await runtime.stop()
    await runtime.stop()

    assert worker.stop_count == 1
    assert runtime.is_started is False


@pytest.mark.asyncio
async def test_runtime_cancels_worker_after_shutdown_timeout() -> None:
    worker = CancellationOnlyWorker()
    runtime = ApplicationRuntime(
        shutdown_timeout_seconds=0.01,
    )
    runtime.register_worker(
        name="cancellation-only-worker",
        worker=worker,
    )

    await runtime.start()
    await asyncio.wait_for(worker.started.wait(), timeout=1.0)

    await runtime.stop()

    await asyncio.wait_for(worker.cancelled.wait(), timeout=1.0)

    assert worker.stop_count == 1
    assert runtime.is_started is False
    assert runtime.is_stopping is False


@pytest.mark.asyncio
async def test_runtime_observes_worker_failure_during_shutdown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    worker = FailingWorker()
    runtime = ApplicationRuntime(
        shutdown_timeout_seconds=1.0,
    )
    runtime.register_worker(
        name="failing-worker",
        worker=worker,
    )

    await runtime.start()
    await asyncio.wait_for(worker.started.wait(), timeout=1.0)

    # Allow the managed task to finish with its exception before shutdown.
    await asyncio.sleep(0)

    await runtime.stop()

    assert worker.stop_count == 1
    assert runtime.is_started is False
    assert "Background worker terminated unexpectedly" in caplog.text
    assert "Background worker task finished with error" in caplog.text


@pytest.mark.asyncio
async def test_runtime_rejects_worker_registration_after_start() -> None:
    first_worker = GracefulWorker()
    second_worker = GracefulWorker()
    runtime = ApplicationRuntime(
        shutdown_timeout_seconds=1.0,
    )
    runtime.register_worker(
        name="first-worker",
        worker=first_worker,
    )

    await runtime.start()
    await asyncio.wait_for(first_worker.started.wait(), timeout=1.0)

    try:
        with pytest.raises(
            RuntimeError,
            match="workers cannot be registered after runtime startup",
        ):
            runtime.register_worker(
                name="second-worker",
                worker=second_worker,
            )
    finally:
        await runtime.stop()
