from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from globalroamer_platform.domain.models.embedding_record import (
    EmbeddingRecord,
)


TENANT_ID = "tenant-001"
TRACE_ID = "trace-001"
TESTCASE_ID = "TC-EMBEDDING-001"
MODEL_NAME = "text-embedding-test"
MODEL_VERSION = "1.0"
CHUNK_ID = UUID("79d39a81-29c0-4cc9-a857-bd41be3aa0ca")
RECORD_ID = UUID("2d46d78f-1eac-4dd8-9ed9-2b64659291c5")

EMBEDDING = (
    0.125,
    -0.25,
    0.5,
)

CONTENT_CHECKSUM = (
    "75f8b2a934af289f1b826b4776bafb17"
    "9f25df1ecdf73d9409f89263eea4e0f1"
)

CREATED_AT = datetime(
    2026,
    7,
    22,
    12,
    0,
    0,
    tzinfo=timezone.utc,
)


def create_embedding_record(
    **overrides,
) -> EmbeddingRecord:
    """Create a valid EmbeddingRecord with optional field overrides."""

    values = {
        "tenant_id": TENANT_ID,
        "trace_id": TRACE_ID,
        "testcase_id": TESTCASE_ID,
        "chunk_id": CHUNK_ID,
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "embedding": EMBEDDING,
        "content_checksum": CONTENT_CHECKSUM,
        "record_id": RECORD_ID,
        "created_at": CREATED_AT,
    }
    values.update(overrides)

    return EmbeddingRecord.create(
        **values,
    )


def test_create_builds_complete_embedding_record() -> None:
    """A valid embedding record is created with normalized fields."""

    record = create_embedding_record()

    assert record.id == RECORD_ID
    assert record.tenant_id == TENANT_ID
    assert record.trace_id == TRACE_ID
    assert record.testcase_id == TESTCASE_ID
    assert record.chunk_id == CHUNK_ID

    assert record.model_name == MODEL_NAME
    assert record.model_version == MODEL_VERSION

    assert record.dimensions == 3
    assert record.embedding == EMBEDDING
    assert isinstance(record.embedding, tuple)

    assert record.content_checksum == CONTENT_CHECKSUM
    assert record.created_at == CREATED_AT


def test_create_generates_id_and_timestamp_when_not_supplied() -> None:
    """The factory generates identity and creation time by default."""

    before = datetime.now(timezone.utc)

    record = create_embedding_record(
        record_id=None,
        created_at=None,
    )

    after = datetime.now(timezone.utc)

    assert isinstance(record.id, UUID)
    assert before <= record.created_at <= after


def test_create_strips_string_fields() -> None:
    """String identity and model fields are stripped."""

    record = create_embedding_record(
        tenant_id="  tenant-001  ",
        trace_id="  trace-001  ",
        testcase_id="  TC-EMBEDDING-001  ",
        model_name="  text-embedding-test  ",
        model_version="  1.0  ",
        content_checksum=f"  {CONTENT_CHECKSUM.upper()}  ",
    )

    assert record.tenant_id == TENANT_ID
    assert record.trace_id == TRACE_ID
    assert record.testcase_id == TESTCASE_ID
    assert record.model_name == MODEL_NAME
    assert record.model_version == MODEL_VERSION
    assert record.content_checksum == CONTENT_CHECKSUM


def test_create_supports_null_testcase_id() -> None:
    """The testcase identity is optional."""

    record = create_embedding_record(
        testcase_id=None,
    )

    assert record.testcase_id is None


def test_create_converts_numeric_embedding_values_to_float() -> None:
    """Integer and floating-point vector values are normalized to floats."""

    record = create_embedding_record(
        embedding=(
            1,
            -2.5,
            3,
        ),
    )

    assert record.embedding == (
        1.0,
        -2.5,
        3.0,
    )
    assert record.dimensions == 3


def test_create_copies_mutable_embedding_sequence() -> None:
    """Mutating the source list cannot change the immutable domain record."""

    source_embedding = [
        0.1,
        0.2,
        0.3,
    ]

    record = create_embedding_record(
        embedding=source_embedding,
    )

    source_embedding.append(
        0.4,
    )

    assert record.embedding == (
        0.1,
        0.2,
        0.3,
    )
    assert record.dimensions == 3


def test_created_at_is_normalized_to_utc() -> None:
    """A timezone-aware timestamp is converted to UTC."""

    source_timezone = timezone(
        timedelta(hours=3),
    )
    source_timestamp = datetime(
        2026,
        7,
        22,
        15,
        0,
        0,
        tzinfo=source_timezone,
    )

    record = create_embedding_record(
        created_at=source_timestamp,
    )

    assert record.created_at == CREATED_AT
    assert record.created_at.tzinfo == timezone.utc


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        (
            "tenant_id",
            123,
        ),
        (
            "trace_id",
            False,
        ),
        (
            "testcase_id",
            123,
        ),
        (
            "model_name",
            object(),
        ),
        (
            "model_version",
            1,
        ),
    ],
)
def test_create_rejects_non_string_identity_fields(
    field_name: str,
    value: object,
) -> None:
    """Identity and model fields must be strings when supplied."""

    with pytest.raises(
        TypeError,
        match=rf"{field_name} must be a string",
    ):
        create_embedding_record(
            **{
                field_name: value,
            }
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "tenant_id",
        "trace_id",
        "testcase_id",
        "model_name",
        "model_version",
    ],
)
@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
    ],
)
def test_create_rejects_empty_string_fields(
    field_name: str,
    value: str,
) -> None:
    """Required strings and a supplied testcase ID cannot be empty."""

    with pytest.raises(
        ValueError,
        match=rf"{field_name} must not be empty",
    ):
        create_embedding_record(
            **{
                field_name: value,
            }
        )


@pytest.mark.parametrize(
    "chunk_id",
    [
        None,
        "chunk-id",
        123,
        False,
    ],
)
def test_create_rejects_invalid_chunk_id(
    chunk_id: object,
) -> None:
    """The referenced trace chunk identity must be a UUID."""

    with pytest.raises(
        TypeError,
        match="chunk_id must be a UUID",
    ):
        create_embedding_record(
            chunk_id=chunk_id,
        )


@pytest.mark.parametrize(
    "record_id",
    [
        "record-id",
        123,
        False,
    ],
)
def test_create_rejects_invalid_record_id(
    record_id: object,
) -> None:
    """A supplied embedding record identity must be a UUID."""

    with pytest.raises(
        TypeError,
        match="record_id must be a UUID",
    ):
        create_embedding_record(
            record_id=record_id,
        )


@pytest.mark.parametrize(
    "embedding",
    [
        "0.1,0.2",
        b"0.1,0.2",
        bytearray(b"0.1,0.2"),
        {
            0.1,
            0.2,
        },
        123,
        None,
    ],
)
def test_create_rejects_invalid_embedding_container(
    embedding: object,
) -> None:
    """The vector must be a non-string sequence."""

    with pytest.raises(
        TypeError,
        match="embedding must be a sequence of numbers",
    ):
        create_embedding_record(
            embedding=embedding,
        )


@pytest.mark.parametrize(
    "embedding",
    [
        (),
        [],
    ],
)
def test_create_rejects_empty_embedding(
    embedding,
) -> None:
    """The vector must contain at least one dimension."""

    with pytest.raises(
        ValueError,
        match="embedding must not be empty",
    ):
        create_embedding_record(
            embedding=embedding,
        )


@pytest.mark.parametrize(
    "embedding",
    [
        (
            0.1,
            "0.2",
        ),
        (
            0.1,
            None,
        ),
        (
            0.1,
            True,
        ),
        (
            object(),
            0.2,
        ),
    ],
)
def test_create_rejects_non_numeric_embedding_values(
    embedding,
) -> None:
    """Every vector component must be a real number."""

    with pytest.raises(
        TypeError,
        match=r"embedding values must be numeric: "
        r"invalid value at index \d+",
    ):
        create_embedding_record(
            embedding=embedding,
        )


@pytest.mark.parametrize(
    "invalid_value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_create_rejects_non_finite_embedding_values(
    invalid_value: float,
) -> None:
    """NaN and infinite vector values are not valid embeddings."""

    with pytest.raises(
        ValueError,
        match=r"embedding values must be finite: "
        r"invalid value at index 1",
    ):
        create_embedding_record(
            embedding=(
                0.1,
                invalid_value,
                0.3,
            ),
        )


@pytest.mark.parametrize(
    "content_checksum",
    [
        123,
        None,
        False,
    ],
)
def test_create_rejects_non_string_checksum(
    content_checksum: object,
) -> None:
    """The source-content checksum must be a string."""

    with pytest.raises(
        TypeError,
        match="content_checksum must be a string",
    ):
        create_embedding_record(
            content_checksum=content_checksum,
        )


@pytest.mark.parametrize(
    "content_checksum",
    [
        "",
        "   ",
    ],
)
def test_create_rejects_empty_checksum(
    content_checksum: str,
) -> None:
    """The source-content checksum cannot be empty."""

    with pytest.raises(
        ValueError,
        match="content_checksum must not be empty",
    ):
        create_embedding_record(
            content_checksum=content_checksum,
        )


@pytest.mark.parametrize(
    "content_checksum",
    [
        "abc",
        "a" * 63,
        "a" * 65,
        "z" * 64,
    ],
)
def test_create_rejects_invalid_sha256_checksum(
    content_checksum: str,
) -> None:
    """The checksum must be exactly one valid SHA-256 hexadecimal digest."""

    with pytest.raises(
        ValueError,
        match=(
            "content_checksum must be a SHA-256 "
            "hexadecimal digest"
        ),
    ):
        create_embedding_record(
            content_checksum=content_checksum,
        )


@pytest.mark.parametrize(
    "created_at",
    [
        "2026-07-22T12:00:00Z",
        123,
        False,
    ],
)
def test_create_rejects_non_datetime_created_at(
    created_at: object,
) -> None:
    """The creation timestamp must be a datetime."""

    with pytest.raises(
        TypeError,
        match="created_at must be a datetime",
    ):
        create_embedding_record(
            created_at=created_at,
        )


def test_create_rejects_naive_created_at() -> None:
    """Naive timestamps are rejected to avoid timezone ambiguity."""

    with pytest.raises(
        ValueError,
        match="created_at must be timezone-aware",
    ):
        create_embedding_record(
            created_at=datetime(
                2026,
                7,
                22,
                12,
                0,
                0,
            ),
        )


def test_belongs_to_returns_true_for_matching_tenant_trace() -> None:
    """The ownership helper recognizes the matching tenant trace."""

    record = create_embedding_record()

    assert record.belongs_to(
        tenant_id=TENANT_ID,
        trace_id=TRACE_ID,
    )


@pytest.mark.parametrize(
    ("tenant_id", "trace_id"),
    [
        (
            "different-tenant",
            TRACE_ID,
        ),
        (
            TENANT_ID,
            "different-trace",
        ),
        (
            "different-tenant",
            "different-trace",
        ),
    ],
)
def test_belongs_to_returns_false_for_different_identity(
    tenant_id: str,
    trace_id: str,
) -> None:
    """The ownership helper rejects a different tenant or trace."""

    record = create_embedding_record()

    assert not record.belongs_to(
        tenant_id=tenant_id,
        trace_id=trace_id,
    )


def test_uses_model_returns_true_for_matching_model() -> None:
    """The model helper recognizes the generating model identity."""

    record = create_embedding_record()

    assert record.uses_model(
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
    )


@pytest.mark.parametrize(
    ("model_name", "model_version"),
    [
        (
            "different-model",
            MODEL_VERSION,
        ),
        (
            MODEL_NAME,
            "2.0",
        ),
        (
            "different-model",
            "2.0",
        ),
    ],
)
def test_uses_model_returns_false_for_different_model_identity(
    model_name: str,
    model_version: str,
) -> None:
    """The model helper requires both name and version to match."""

    record = create_embedding_record()

    assert not record.uses_model(
        model_name=model_name,
        model_version=model_version,
    )


def test_model_identity_returns_name_and_version() -> None:
    """The model identity helper returns a stable tuple."""

    record = create_embedding_record()

    assert record.model_identity == (
        MODEL_NAME,
        MODEL_VERSION,
    )


def test_embedding_record_is_immutable() -> None:
    """Embedding records cannot be modified after creation."""

    record = create_embedding_record()

    with pytest.raises(
        AttributeError,
    ):
        record.tenant_id = "different-tenant"  # type: ignore[misc]
