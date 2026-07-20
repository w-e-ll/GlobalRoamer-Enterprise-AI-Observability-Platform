from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from globalroamer_platform.application.outbox.publish_pending_outbox_messages import (
    PublishPendingOutboxMessagesCommand,
    PublishPendingOutboxMessagesResult,
)
from globalroamer_platform.workers.outbox_worker import (
    OutboxWorker,
    OutboxWorkerSettings,
)


def make_result(
    *,
    selected_count: int = 0,
    published_count: int = 0,
    retry_scheduled_count: int = 0,
    permanently_failed_count: int = 0,
) -> PublishPendingOutboxMessagesResult:
    return PublishPendingOutboxMessagesResult(
        selected_count=selected_count,
        published_count=published_count,
        retry_scheduled_count=retry_scheduled_count,
        permanently_failed_count=permanently_failed_count,
    )


def make_worker(
    *,
    publisher: AsyncMock | None = None,
    commit: AsyncMock | None = None,
    rollback: AsyncMock | None = None,
    sleep: AsyncMock | None = None,
    settings: OutboxWorkerSettings | None = None,
) -> tuple[
    OutboxWorker,
    AsyncMock,
    AsyncMock,
    AsyncMock,
    AsyncMock,
]:
    publisher = publisher or AsyncMock()
    commit = commit or AsyncMock()
    rollback = rollback or AsyncMock()
    sleep = sleep or AsyncMock()

    worker = OutboxWorker(
        publisher=publisher,
        settings=settings or OutboxWorkerSettings(),
        commit=commit,
        rollback=rollback,
        sleep=sleep,
    )

    return worker, publisher, commit, rollback, sleep


def test_settings_use_defaults() -> None:
    settings = OutboxWorkerSettings()

    assert settings.poll_interval_seconds == 1.0
    assert settings.batch_size == 100
    assert settings.max_attempts == 5
    assert settings.initial_retry_delay_seconds == 5.0


@pytest.mark.parametrize(
    ("field_name", "field_value", "expected_message"),
    [
        (
            "poll_interval_seconds",
            0,
            "poll_interval_seconds must be greater than zero",
        ),
        (
            "batch_size",
            0,
            "batch_size must be greater than zero",
        ),
        (
            "max_attempts",
            0,
            "max_attempts must be greater than zero",
        ),
        (
            "initial_retry_delay_seconds",
            0,
            "initial_retry_delay_seconds must be greater than zero",
        ),
    ],
)
def test_settings_reject_non_positive_values(
    field_name: str,
    field_value: int,
    expected_message: str,
) -> None:
    values: dict[str, float | int] = {
        "poll_interval_seconds": 1.0,
        "batch_size": 100,
        "max_attempts": 5,
        "initial_retry_delay_seconds": 5.0,
    }
    values[field_name] = field_value

    with pytest.raises(
        ValueError,
        match=expected_message,
    ):
        OutboxWorkerSettings(**values)


@pytest.mark.anyio
async def test_run_once_executes_publisher_and_commits() -> None:
    settings = OutboxWorkerSettings(
        batch_size=25,
        max_attempts=7,
        initial_retry_delay_seconds=3.0,
    )

    worker, publisher, commit, rollback, _ = make_worker(
        settings=settings,
    )

    expected_result = make_result(
        selected_count=2,
        published_count=2,
    )
    publisher.execute.return_value = expected_result

    result = await worker.run_once()

    assert result == expected_result

    publisher.execute.assert_awaited_once()

    command = publisher.execute.await_args.args[0]

    assert isinstance(
        command,
        PublishPendingOutboxMessagesCommand,
    )
    assert command.batch_size == 25
    assert command.max_attempts == 7
    assert command.initial_retry_delay_seconds == 3.0

    commit.assert_awaited_once_with()
    rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_run_once_works_without_transaction_callbacks() -> None:
    publisher = AsyncMock()
    publisher.execute.return_value = make_result()

    worker = OutboxWorker(
        publisher=publisher,
    )

    result = await worker.run_once()

    assert result.selected_count == 0
    publisher.execute.assert_awaited_once()


@pytest.mark.anyio
async def test_run_once_rolls_back_when_publisher_fails() -> None:
    worker, publisher, commit, rollback, _ = make_worker()

    publisher.execute.side_effect = RuntimeError(
        "database unavailable",
    )

    with pytest.raises(
        RuntimeError,
        match="database unavailable",
    ):
        await worker.run_once()

    commit.assert_not_awaited()
    rollback.assert_awaited_once_with()


@pytest.mark.anyio
async def test_run_once_propagates_commit_failure_and_rolls_back() -> None:
    worker, publisher, commit, rollback, _ = make_worker()

    publisher.execute.return_value = make_result(
        selected_count=1,
        published_count=1,
    )
    commit.side_effect = RuntimeError(
        "commit failed",
    )

    with pytest.raises(
        RuntimeError,
        match="commit failed",
    ):
        await worker.run_once()

    publisher.execute.assert_awaited_once()
    commit.assert_awaited_once_with()
    rollback.assert_awaited_once_with()


def test_stop_sets_stopping_state() -> None:
    worker, _, _, _, _ = make_worker()

    assert worker.is_stopping is False

    worker.stop()

    assert worker.is_stopping is True


@pytest.mark.anyio
async def test_wait_for_next_poll_returns_after_timeout() -> None:
    worker, _, _, _, _ = make_worker(
        settings=OutboxWorkerSettings(
            poll_interval_seconds=0.001,
        ),
    )

    await worker._wait_for_next_poll()


@pytest.mark.anyio
async def test_wait_for_next_poll_returns_when_stop_is_requested() -> None:
    worker, _, _, _, _ = make_worker(
        settings=OutboxWorkerSettings(
            poll_interval_seconds=60,
        ),
    )

    worker.stop()

    await worker._wait_for_next_poll()

    assert worker.is_stopping is True


@pytest.mark.anyio
async def test_run_forever_waits_when_batch_is_empty() -> None:
    worker, publisher, commit, rollback, _ = make_worker()

    publisher.execute.return_value = make_result(
        selected_count=0,
    )

    wait_for_next_poll = AsyncMock(
        side_effect=lambda: worker.stop(),
    )
    worker._wait_for_next_poll = wait_for_next_poll

    await worker.run_forever()

    publisher.execute.assert_awaited_once()
    commit.assert_awaited_once()
    rollback.assert_not_awaited()
    wait_for_next_poll.assert_awaited_once()


@pytest.mark.anyio
async def test_run_forever_continues_immediately_for_non_empty_batch() -> None:
    worker, publisher, commit, rollback, _ = make_worker()

    first_result = make_result(
        selected_count=1,
        published_count=1,
    )
    second_result = make_result(
        selected_count=0,
    )

    publisher.execute.side_effect = [
        first_result,
        second_result,
    ]

    wait_for_next_poll = AsyncMock(
        side_effect=lambda: worker.stop(),
    )
    worker._wait_for_next_poll = wait_for_next_poll

    await worker.run_forever()

    assert publisher.execute.await_count == 2
    assert commit.await_count == 2
    rollback.assert_not_awaited()

    # The worker does not wait after the first non-empty batch. It waits only
    # after the second empty batch.
    wait_for_next_poll.assert_awaited_once()


@pytest.mark.anyio
async def test_run_forever_waits_and_continues_after_batch_failure() -> None:
    worker, publisher, commit, rollback, _ = make_worker()

    publisher.execute.side_effect = [
        RuntimeError("temporary database failure"),
        make_result(selected_count=0),
    ]

    async def stop_after_wait() -> None:
        if publisher.execute.await_count >= 2:
            worker.stop()

    wait_for_next_poll = AsyncMock(
        side_effect=stop_after_wait,
    )
    worker._wait_for_next_poll = wait_for_next_poll

    await worker.run_forever()

    assert publisher.execute.await_count == 2
    assert rollback.await_count == 1
    assert commit.await_count == 1
    assert wait_for_next_poll.await_count == 2


@pytest.mark.anyio
async def test_run_forever_propagates_cancellation() -> None:
    worker, publisher, commit, rollback, _ = make_worker()

    publisher.execute.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await worker.run_forever()

    commit.assert_not_awaited()
    rollback.assert_awaited_once()
