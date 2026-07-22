from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.runtime.session_scoped_event_handler import (
    SessionScopedEventHandler,
)


def make_event(
    event_type: str = "TRACE_PARSED",
) -> EventEnvelope:
    return EventEnvelope(
        event_id=UUID(
            "00000000-0000-0000-0000-000000000001"
        ),
        event_type=event_type,
        correlation_id="correlation-1",
        tenant_id="tenant-1",
        occurred_at=datetime.now(UTC),
        producer="test-suite",
        payload={},
    )


class FakeSessionContext:
    """Async context manager returning the supplied fake session."""

    def __init__(
        self,
        session: Any,
    ) -> None:
        self._session = session

    async def __aenter__(self) -> Any:
        return self._session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        return None


def make_session_factory(
    session: Any,
) -> Mock:
    factory = Mock()
    factory.return_value = FakeSessionContext(session)
    return factory


@pytest.mark.asyncio
async def test_handle_commits_after_successful_event_handling() -> None:
    event = make_event()

    produced_event = EventEnvelope(
        event_id=UUID(
            "00000000-0000-0000-0000-000000000002"
        ),
        event_type="TRACE_NORMALIZED",
        correlation_id=event.correlation_id,
        causation_id=event.event_id,
        tenant_id=event.tenant_id,
        occurred_at=datetime.now(UTC),
        producer="normalizer-worker",
        payload={},
    )

    session = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    handler = Mock()
    handler.handle = AsyncMock(
        return_value=produced_event,
    )

    handler_factory = Mock(
        return_value=handler,
    )

    session_factory = make_session_factory(session)

    scoped_handler = SessionScopedEventHandler(
        session_factory=session_factory,
        handler_factory=handler_factory,
    )

    result = await scoped_handler.handle(event)

    assert result == produced_event

    session_factory.assert_called_once_with()
    handler_factory.assert_called_once_with(session)
    handler.handle.assert_awaited_once_with(event)
    session.commit.assert_awaited_once_with()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_commits_when_handler_returns_none() -> None:
    event = make_event()

    session = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    handler = Mock()
    handler.handle = AsyncMock(
        return_value=None,
    )

    scoped_handler = SessionScopedEventHandler(
        session_factory=make_session_factory(session),
        handler_factory=Mock(return_value=handler),
    )

    result = await scoped_handler.handle(event)

    assert result is None
    session.commit.assert_awaited_once_with()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_rolls_back_and_reraises_on_failure() -> None:
    event = make_event()
    expected_error = RuntimeError(
        "event handling failed"
    )

    session = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    handler = Mock()
    handler.handle = AsyncMock(
        side_effect=expected_error,
    )

    scoped_handler = SessionScopedEventHandler(
        session_factory=make_session_factory(session),
        handler_factory=Mock(return_value=handler),
    )

    with pytest.raises(
        RuntimeError,
        match="event handling failed",
    ) as captured:
        await scoped_handler.handle(event)

    assert captured.value is expected_error
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_handle_rolls_back_and_reraises_on_cancellation() -> None:
    event = make_event()

    session = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    handler = Mock()
    handler.handle = AsyncMock(
        side_effect=asyncio.CancelledError,
    )

    scoped_handler = SessionScopedEventHandler(
        session_factory=make_session_factory(session),
        handler_factory=Mock(return_value=handler),
    )

    with pytest.raises(asyncio.CancelledError):
        await scoped_handler.handle(event)

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_rollback_failure_does_not_mask_handler_failure() -> None:
    event = make_event()
    expected_error = RuntimeError(
        "primary handler failure"
    )

    session = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock(
        side_effect=RuntimeError(
            "rollback failure"
        )
    )

    handler = Mock()
    handler.handle = AsyncMock(
        side_effect=expected_error,
    )

    scoped_handler = SessionScopedEventHandler(
        session_factory=make_session_factory(session),
        handler_factory=Mock(return_value=handler),
    )

    with pytest.raises(
        RuntimeError,
        match="primary handler failure",
    ) as captured:
        await scoped_handler.handle(event)

    assert captured.value is expected_error
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_commit_failure_triggers_rollback_and_is_reraised() -> None:
    event = make_event()
    expected_error = RuntimeError(
        "commit failed"
    )

    session = Mock()
    session.commit = AsyncMock(
        side_effect=expected_error,
    )
    session.rollback = AsyncMock()

    handler = Mock()
    handler.handle = AsyncMock(
        return_value=None,
    )

    scoped_handler = SessionScopedEventHandler(
        session_factory=make_session_factory(session),
        handler_factory=Mock(return_value=handler),
    )

    with pytest.raises(
        RuntimeError,
        match="commit failed",
    ) as captured:
        await scoped_handler.handle(event)

    assert captured.value is expected_error
    handler.handle.assert_awaited_once_with(event)
    session.commit.assert_awaited_once_with()
    session.rollback.assert_awaited_once_with()
