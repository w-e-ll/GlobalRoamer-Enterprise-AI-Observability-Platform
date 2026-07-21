from __future__ import annotations

from uuid import UUID

import pytest

from globalroamer_platform.domain.models.trace_chunk import (
    TraceChunk,
)
from globalroamer_platform.domain.services.trace_chunker import (
    TraceChunker,
)
from globalroamer_platform.infrastructure.database.models import (
    TraceChunkModel,
)
from globalroamer_platform.infrastructure.persistence.trace_chunk_mapper import (
    TraceChunkMapper,
)
from tests.domain.services.test_trace_chunker import (
    make_event,
)


def make_chunk() -> TraceChunk:
    """
    Build a realistic TraceChunk through the domain service instead of
    duplicating TraceChunk construction details inside mapper tests.
    """

    events = (
        make_event(
            sequence_number=1,
            event_name="attach_request",
            normalized_message="Attach request received",
            cause="network-registration",
            tags=("mobility", "attach"),
            retry_recommended=False,
        ),
        make_event(
            sequence_number=2,
            event_name="attach_reject",
            normalized_message="Attach request rejected",
            cause="roaming-not-allowed",
            tags=("mobility", "failure"),
            retry_recommended=True,
        ),
    )

    chunks = TraceChunker(
        chunk_size=10_000,
        chunk_overlap=0,
    ).chunk(events)

    assert len(chunks) == 1

    return chunks[0]


def test_to_model_maps_all_scalar_fields() -> None:
    chunk = make_chunk()

    model = TraceChunkMapper.to_model(chunk)

    assert isinstance(model, TraceChunkModel)

    assert model.id == chunk.id
    assert model.tenant_id == chunk.tenant_id
    assert model.trace_id == chunk.trace_id
    assert model.testcase_id == chunk.testcase_id
    assert model.chunk_index == chunk.chunk_index
    assert model.text == chunk.text
    assert model.event_count == chunk.event_count
    assert model.has_failure == chunk.has_failure
    assert (
        model.has_high_severity
        == chunk.has_high_severity
    )
    assert (
        model.has_retry_recommended
        == chunk.has_retry_recommended
    )
    assert model.created_at == chunk.created_at
    assert model.content_hash == chunk.content_hash


def test_to_model_converts_domain_tuples_to_lists() -> None:
    chunk = make_chunk()

    model = TraceChunkMapper.to_model(chunk)

    assert isinstance(model.event_ids, list)
    assert isinstance(model.event_names, list)
    assert isinstance(model.event_families, list)
    assert isinstance(model.severities, list)
    assert isinstance(model.causes, list)
    assert isinstance(model.tags, list)

    assert model.event_names == list(
        chunk.event_names
    )
    assert model.event_families == list(
        chunk.event_families
    )
    assert model.severities == list(
        chunk.severities
    )
    assert model.causes == list(chunk.causes)
    assert model.tags == list(chunk.tags)


def test_to_model_converts_event_ids_to_strings() -> None:
    chunk = make_chunk()

    model = TraceChunkMapper.to_model(chunk)

    assert model.event_ids == [
        str(event_id)
        for event_id in chunk.event_ids
    ]

    assert all(
        isinstance(event_id, str)
        for event_id in model.event_ids
    )


def test_to_domain_maps_all_scalar_fields() -> None:
    original = make_chunk()
    model = TraceChunkMapper.to_model(original)

    chunk = TraceChunkMapper.to_domain(model)

    assert isinstance(chunk, TraceChunk)

    assert chunk.id == original.id
    assert chunk.tenant_id == original.tenant_id
    assert chunk.trace_id == original.trace_id
    assert chunk.testcase_id == original.testcase_id
    assert chunk.chunk_index == original.chunk_index
    assert chunk.text == original.text
    assert chunk.event_count == original.event_count
    assert chunk.has_failure == original.has_failure
    assert (
        chunk.has_high_severity
        == original.has_high_severity
    )
    assert (
        chunk.has_retry_recommended
        == original.has_retry_recommended
    )
    assert chunk.created_at == original.created_at
    assert chunk.content_hash == original.content_hash


def test_to_domain_converts_persistence_lists_to_tuples() -> None:
    original = make_chunk()
    model = TraceChunkMapper.to_model(original)

    chunk = TraceChunkMapper.to_domain(model)

    assert isinstance(chunk.event_ids, tuple)
    assert isinstance(chunk.event_names, tuple)
    assert isinstance(chunk.event_families, tuple)
    assert isinstance(chunk.severities, tuple)
    assert isinstance(chunk.causes, tuple)
    assert isinstance(chunk.tags, tuple)

    assert chunk.event_names == original.event_names
    assert (
        chunk.event_families
        == original.event_families
    )
    assert chunk.severities == original.severities
    assert chunk.causes == original.causes
    assert chunk.tags == original.tags


def test_to_domain_converts_event_ids_to_uuids() -> None:
    original = make_chunk()
    model = TraceChunkMapper.to_model(original)

    chunk = TraceChunkMapper.to_domain(model)

    assert chunk.event_ids == original.event_ids

    assert all(
        isinstance(event_id, UUID)
        for event_id in chunk.event_ids
    )


def test_mapper_round_trip_preserves_domain_object() -> None:
    original = make_chunk()

    restored = TraceChunkMapper.to_domain(
        TraceChunkMapper.to_model(original)
    )

    assert restored == original


def test_to_model_creates_independent_collection_values() -> None:
    chunk = make_chunk()

    model = TraceChunkMapper.to_model(chunk)

    model.event_names.append("database-only-value")
    model.tags.append("database-only-tag")

    assert (
        "database-only-value"
        not in chunk.event_names
    )
    assert "database-only-tag" not in chunk.tags


def test_to_domain_creates_immutable_collection_values() -> None:
    original = make_chunk()
    model = TraceChunkMapper.to_model(original)

    restored = TraceChunkMapper.to_domain(model)

    model.event_names.append("later-database-value")
    model.tags.append("later-database-tag")

    assert (
        "later-database-value"
        not in restored.event_names
    )
    assert "later-database-tag" not in restored.tags


def test_to_model_rejects_invalid_domain_type() -> None:
    with pytest.raises(
        TypeError,
        match="chunk must be a TraceChunk",
    ):
        TraceChunkMapper.to_model(
            object(),  # type: ignore[arg-type]
        )


def test_to_domain_rejects_invalid_model_type() -> None:
    with pytest.raises(
        TypeError,
        match="model must be a TraceChunkModel",
    ):
        TraceChunkMapper.to_domain(
            object(),  # type: ignore[arg-type]
        )


def test_to_domain_rejects_invalid_event_id() -> None:
    chunk = make_chunk()
    model = TraceChunkMapper.to_model(chunk)

    model.event_ids = ["not-a-valid-uuid"]

    with pytest.raises(ValueError):
        TraceChunkMapper.to_domain(model)
