from __future__ import annotations

from typing import Sequence

import pytest

from globalroamer_platform.application.ports.embedding_provider import (
    EmbeddingBatch,
    EmbeddingProvider,
    EmbeddingProviderError,
)


MODEL_NAME = "text-embedding-test"
MODEL_VERSION = "1.0"

VECTORS = (
    (
        0.1,
        0.2,
        0.3,
    ),
    (
        -0.4,
        0.5,
        0.6,
    ),
)


def create_embedding_batch(
    **overrides,
) -> EmbeddingBatch:
    """Create a valid embedding batch with optional overrides."""

    values = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "vectors": VECTORS,
    }
    values.update(overrides)

    return EmbeddingBatch.create(
        **values,
    )


def test_create_builds_complete_embedding_batch() -> None:
    """A valid provider response is converted to an embedding batch."""

    batch = create_embedding_batch()

    assert batch.model_name == MODEL_NAME
    assert batch.model_version == MODEL_VERSION
    assert batch.dimensions == 3
    assert batch.count == 2
    assert batch.vectors == VECTORS


def test_create_strips_model_identity_fields() -> None:
    """Model name and version are normalized."""

    batch = create_embedding_batch(
        model_name="  text-embedding-test  ",
        model_version="  1.0  ",
    )

    assert batch.model_name == MODEL_NAME
    assert batch.model_version == MODEL_VERSION


def test_create_converts_vector_values_to_float() -> None:
    """Numeric vector values are normalized to floats."""

    batch = create_embedding_batch(
        vectors=(
            (
                1,
                2.5,
                -3,
            ),
            (
                4,
                5,
                6.25,
            ),
        ),
    )

    assert batch.vectors == (
        (
            1.0,
            2.5,
            -3.0,
        ),
        (
            4.0,
            5.0,
            6.25,
        ),
    )


def test_create_converts_outer_and_inner_sequences_to_tuples() -> None:
    """The created batch does not retain mutable provider collections."""

    source_vectors = [
        [
            0.1,
            0.2,
        ],
        [
            0.3,
            0.4,
        ],
    ]

    batch = create_embedding_batch(
        vectors=source_vectors,
    )

    source_vectors[0].append(
        0.9,
    )
    source_vectors.append(
        [
            0.5,
            0.6,
        ]
    )

    assert batch.vectors == (
        (
            0.1,
            0.2,
        ),
        (
            0.3,
            0.4,
        ),
    )
    assert batch.count == 2
    assert batch.dimensions == 2


def test_dimensions_are_derived_from_first_vector() -> None:
    """Vector dimensions are calculated rather than accepted externally."""

    batch = create_embedding_batch(
        vectors=(
            (
                0.1,
                0.2,
                0.3,
                0.4,
            ),
        ),
    )

    assert batch.dimensions == 4


def test_count_returns_number_of_vectors() -> None:
    """The count property returns the batch size."""

    batch = create_embedding_batch(
        vectors=(
            (
                0.1,
                0.2,
            ),
            (
                0.3,
                0.4,
            ),
            (
                0.5,
                0.6,
            ),
        ),
    )

    assert batch.count == 3


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        (
            "model_name",
            None,
        ),
        (
            "model_name",
            123,
        ),
        (
            "model_name",
            False,
        ),
        (
            "model_version",
            None,
        ),
        (
            "model_version",
            1,
        ),
        (
            "model_version",
            False,
        ),
    ],
)
def test_create_rejects_non_string_model_identity(
    field_name: str,
    value: object,
) -> None:
    """Model identity fields must be strings."""

    with pytest.raises(
        TypeError,
        match=rf"{field_name} must be a string",
    ):
        create_embedding_batch(
            **{
                field_name: value,
            }
        )


@pytest.mark.parametrize(
    "field_name",
    [
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
def test_create_rejects_empty_model_identity(
    field_name: str,
    value: str,
) -> None:
    """Model identity fields cannot be empty."""

    with pytest.raises(
        ValueError,
        match=rf"{field_name} must not be empty",
    ):
        create_embedding_batch(
            **{
                field_name: value,
            }
        )


@pytest.mark.parametrize(
    "vectors",
    [
        (),
        [],
    ],
)
def test_create_rejects_empty_vector_collection(
    vectors,
) -> None:
    """An embedding batch must contain at least one vector."""

    with pytest.raises(
        ValueError,
        match="vectors must not be empty",
    ):
        create_embedding_batch(
            vectors=vectors,
        )


@pytest.mark.parametrize(
    "vectors",
    [
        (
            (),
        ),
        (
            [],
        ),
    ],
)
def test_create_rejects_empty_embedding_vector(
    vectors,
) -> None:
    """Every embedding vector must contain at least one component."""

    with pytest.raises(
        ValueError,
        match="embedding vectors must not be empty",
    ):
        create_embedding_batch(
            vectors=vectors,
        )


@pytest.mark.parametrize(
    "vectors",
    [
        (
            (
                0.1,
                0.2,
            ),
            (
                0.3,
            ),
        ),
        (
            (
                0.1,
            ),
            (
                0.2,
                0.3,
            ),
        ),
        (
            (
                0.1,
                0.2,
                0.3,
            ),
            (
                0.4,
                0.5,
            ),
        ),
    ],
)
def test_create_rejects_vectors_with_different_dimensions(
    vectors,
) -> None:
    """All vectors in one provider response must share dimensions."""

    with pytest.raises(
        ValueError,
        match=(
            "all embedding vectors must have the same dimensions: "
            r"invalid vector at index \d+"
        ),
    ):
        create_embedding_batch(
            vectors=vectors,
        )


def test_embedding_batch_is_immutable() -> None:
    """Provider response batches cannot be modified after creation."""

    batch = create_embedding_batch()

    with pytest.raises(
        AttributeError,
    ):
        batch.model_name = "different-model"  # type: ignore[misc]


class FakeEmbeddingProvider:
    """Minimal implementation of the application provider port."""

    async def embed(
        self,
        texts: Sequence[str],
    ) -> EmbeddingBatch:
        vectors = tuple(
            (
                float(index),
                float(len(text)),
            )
            for index, text in enumerate(texts)
        )

        return EmbeddingBatch.create(
            model_name=MODEL_NAME,
            model_version=MODEL_VERSION,
            vectors=vectors,
        )


class InvalidEmbeddingProvider:
    """Object that does not implement the embedding provider contract."""

    pass


def test_runtime_checkable_protocol_accepts_provider_implementation() -> None:
    """A structurally compatible object satisfies the runtime protocol."""

    provider = FakeEmbeddingProvider()

    assert isinstance(
        provider,
        EmbeddingProvider,
    )


def test_runtime_checkable_protocol_rejects_incompatible_object() -> None:
    """An object without embed() does not satisfy the provider protocol."""

    provider = InvalidEmbeddingProvider()

    assert not isinstance(
        provider,
        EmbeddingProvider,
    )


@pytest.mark.asyncio
async def test_provider_returns_embedding_batch_in_input_order() -> None:
    """A provider implementation can return vectors preserving text order."""

    provider: EmbeddingProvider = FakeEmbeddingProvider()

    result = await provider.embed(
        (
            "first",
            "second text",
        )
    )

    assert result.count == 2
    assert result.vectors == (
        (
            0.0,
            5.0,
        ),
        (
            1.0,
            11.0,
        ),
    )


def test_embedding_provider_error_is_runtime_error() -> None:
    """Provider failures can be handled as runtime errors."""

    error = EmbeddingProviderError(
        "provider unavailable"
    )

    assert isinstance(
        error,
        RuntimeError,
    )
    assert str(error) == "provider unavailable"
