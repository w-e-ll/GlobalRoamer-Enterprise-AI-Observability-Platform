from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.domain.models.trace_chunk import (
    TraceChunk,
)
from globalroamer_platform.infrastructure.database.models import (
    TraceChunkModel,
)
from globalroamer_platform.infrastructure.persistence.trace_chunk_mapper import (
    TraceChunkMapper,
)
from globalroamer_platform.infrastructure.persistence.trace_chunk_store import (
    TraceChunkStore,
)
from tests.infrastructure.persistence.test_trace_chunk_mapper import (
    make_chunk,
)


def make_session() -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()

    return session


def test_constructor_accepts_async_session() -> None:
    session = make_session()

    store = TraceChunkStore(session)

    assert store._session is session


def test_constructor_rejects_invalid_session() -> None:
    with pytest.raises(
        TypeError,
        match="session must be an AsyncSession",
    ):
        TraceChunkStore(
            object(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_save_adds_mapped_model_to_session() -> None:
    session = make_session()
    store = TraceChunkStore(session)
    chunk = make_chunk()

    await store.save(chunk)

    session.add.assert_called_once()

    model = session.add.call_args.args[0]

    assert isinstance(model, TraceChunkModel)
    assert model.id == chunk.id
    assert model.tenant_id == chunk.tenant_id
    assert model.trace_id == chunk.trace_id
    assert model.chunk_index == chunk.chunk_index


@pytest.mark.asyncio
async def test_save_does_not_commit() -> None:
    session = make_session()
    store = TraceChunkStore(session)

    await store.save(make_chunk())

    session.commit.assert_not_called()
    session.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_save_rejects_invalid_chunk() -> None:
    session = make_session()
    store = TraceChunkStore(session)

    with pytest.raises(
        TypeError,
        match="chunk must be a TraceChunk",
    ):
        await store.save(
            object(),  # type: ignore[arg-type]
        )

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_save_many_adds_all_mapped_models() -> None:
    session = make_session()
    store = TraceChunkStore(session)

    first = make_chunk()
    second = make_chunk()

    await store.save_many(
        (
            first,
            second,
        )
    )

    session.add_all.assert_called_once()

    models = session.add_all.call_args.args[0]

    assert isinstance(models, list)
    assert len(models) == 2
    assert all(
        isinstance(model, TraceChunkModel)
        for model in models
    )

    assert models[0].id == first.id
    assert models[1].id == second.id


@pytest.mark.asyncio
async def test_save_many_accepts_empty_sequence() -> None:
    session = make_session()
    store = TraceChunkStore(session)

    await store.save_many(())

    session.add_all.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunks",
    [
        "not-chunks",
        b"not-chunks",
        object(),
    ],
)
async def test_save_many_rejects_invalid_collection(
    chunks: object,
) -> None:
    session = make_session()
    store = TraceChunkStore(session)

    with pytest.raises(
        TypeError,
        match=(
            "chunks must be a sequence of "
            "TraceChunk objects"
        ),
    ):
        await store.save_many(
            chunks,  # type: ignore[arg-type]
        )

    session.add_all.assert_not_called()


@pytest.mark.asyncio
async def test_save_many_rejects_invalid_item() -> None:
    session = make_session()
    store = TraceChunkStore(session)

    with pytest.raises(
        TypeError,
        match=(
            "all chunks must be TraceChunk objects"
        ),
    ):
        await store.save_many(
            (
                make_chunk(),
                object(),
            )  # type: ignore[arg-type]
        )

    session.add_all.assert_not_called()


@pytest.mark.asyncio
async def test_get_by_id_returns_domain_chunk() -> None:
    session = make_session()
    store = TraceChunkStore(session)

    original = make_chunk()
    model = TraceChunkMapper.to_model(original)

    result = MagicMock()
    result.scalar_one_or_none.return_value = model
    session.execute.return_value = result

    restored = await store.get_by_id(
        original.id
    )

    assert isinstance(restored, TraceChunk)
    assert restored == original

    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_missing() -> None:
    session = make_session()
    store = TraceChunkStore(session)

    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    restored = await store.get_by_id(
        uuid4()
    )

    assert restored is None
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_by_id_rejects_invalid_id() -> None:
    session = make_session()
    store = TraceChunkStore(session)

    with pytest.raises(
        TypeError,
        match="chunk_id must be a UUID",
    ):
        await store.get_by_id(
            "not-a-uuid",  # type: ignore[arg-type]
        )

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_by_trace_returns_mapped_chunks() -> None:
    session = make_session()
    store = TraceChunkStore(session)

    original = make_chunk()
    model = TraceChunkMapper.to_model(original)

    scalar_result = MagicMock()
    scalar_result.all.return_value = [model]

    result = MagicMock()
    result.scalars.return_value = scalar_result

    session.execute.return_value = result

    chunks = await store.list_by_trace(
        tenant_id=original.tenant_id,
        trace_id=original.trace_id,
    )

    assert isinstance(chunks, tuple)
    assert chunks == (original,)

    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_by_trace_returns_empty_tuple() -> None:
    session = make_session()
    store = TraceChunkStore(session)

    scalar_result = MagicMock()
    scalar_result.all.return_value = []

    result = MagicMock()
    result.scalars.return_value = scalar_result

    session.execute.return_value = result

    chunks = await store.list_by_trace(
        tenant_id="tenant-001",
        trace_id="trace-001",
    )

    assert chunks == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tenant_id", "expected_exception", "message"),
    [
        (
            None,
            TypeError,
            "tenant_id must be a string",
        ),
        (
            123,
            TypeError,
            "tenant_id must be a string",
        ),
        (
            "",
            ValueError,
            "tenant_id must not be empty",
        ),
        (
            " ",
            ValueError,
            "tenant_id must not be empty",
        ),
    ],
)
async def test_list_by_trace_validates_tenant_id(
    tenant_id: object,
    expected_exception: type[Exception],
    message: str,
) -> None:
    session = make_session()
    store = TraceChunkStore(session)

    with pytest.raises(
        expected_exception,
        match=message,
    ):
        await store.list_by_trace(
            tenant_id=tenant_id,  # type: ignore[arg-type]
            trace_id="trace-001",
        )

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("trace_id", "expected_exception", "message"),
    [
        (
            None,
            TypeError,
            "trace_id must be a string",
        ),
        (
            123,
            TypeError,
            "trace_id must be a string",
        ),
        (
            "",
            ValueError,
            "trace_id must not be empty",
        ),
        (
            " ",
            ValueError,
            "trace_id must not be empty",
        ),
    ],
)
async def test_list_by_trace_validates_trace_id(
    trace_id: object,
    expected_exception: type[Exception],
    message: str,
) -> None:
    session = make_session()
    store = TraceChunkStore(session)

    with pytest.raises(
        expected_exception,
        match=message,
    ):
        await store.list_by_trace(
            tenant_id="tenant-001",
            trace_id=trace_id,  # type: ignore[arg-type]
        )

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_by_trace_returns_deleted_count() -> None:
    session = make_session()
    store = TraceChunkStore(session)

    result = MagicMock()
    result.rowcount = 3
    session.execute.return_value = result

    deleted_count = await store.delete_by_trace(
        tenant_id="tenant-001",
        trace_id="trace-001",
    )

    assert deleted_count == 3
    session.execute.assert_awaited_once()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_delete_by_trace_returns_zero_for_no_rows() -> None:
    session = make_session()
    store = TraceChunkStore(session)

    result = MagicMock()
    result.rowcount = 0
    session.execute.return_value = result

    deleted_count = await store.delete_by_trace(
        tenant_id="tenant-001",
        trace_id="trace-001",
    )

    assert deleted_count == 0


@pytest.mark.asyncio
async def test_delete_by_trace_handles_missing_rowcount() -> None:
    session = make_session()
    store = TraceChunkStore(session)

    result = MagicMock()
    result.rowcount = None
    session.execute.return_value = result

    deleted_count = await store.delete_by_trace(
        tenant_id="tenant-001",
        trace_id="trace-001",
    )

    assert deleted_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tenant_id", "trace_id"),
    [
        ("", "trace-001"),
        (" ", "trace-001"),
        ("tenant-001", ""),
        ("tenant-001", " "),
    ],
)
async def test_delete_by_trace_validates_identity(
    tenant_id: str,
    trace_id: str,
) -> None:
    session = make_session()
    store = TraceChunkStore(session)

    with pytest.raises(ValueError):
        await store.delete_by_trace(
            tenant_id=tenant_id,
            trace_id=trace_id,
        )

    session.execute.assert_not_awaited()
