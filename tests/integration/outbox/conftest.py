"""Shared fixtures for transactional outbox integration tests."""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy import delete

from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)
from globalroamer_platform.infrastructure.models.outbox_message import (
    OutboxMessageModel,
)


@pytest_asyncio.fixture(autouse=True)
async def clean_outbox_table() -> None:
    """Ensure every outbox integration test starts with an empty table.

    The production outbox repository intentionally selects globally
    available messages. Integration tests therefore require database
    isolation so pending messages left by another test or an earlier test
    run cannot be selected instead of the message created by the current
    test.
    """

    await _delete_all_outbox_messages()

    try:
        yield
    finally:
        await _delete_all_outbox_messages()


async def _delete_all_outbox_messages() -> None:
    """Delete and commit all transactional outbox records."""

    async with async_session_factory() as session:
        await session.execute(
            delete(OutboxMessageModel),
        )
        await session.commit()
