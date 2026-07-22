"""Application port for generating vector embeddings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    """
    Embedding provider response for one ordered batch of input texts.

    The vectors must preserve the same order as the input texts supplied to
    the provider.
    """

    model_name: str
    model_version: str
    dimensions: int
    vectors: tuple[tuple[float, ...], ...]

    @classmethod
    def create(
        cls,
        *,
        model_name: str,
        model_version: str,
        vectors: Sequence[Sequence[float]],
    ) -> EmbeddingBatch:
        """Create and validate a provider-neutral embedding batch."""

        normalized_model_name = cls._require_non_empty_string(
            model_name,
            field_name="model_name",
        )
        normalized_model_version = cls._require_non_empty_string(
            model_version,
            field_name="model_version",
        )

        normalized_vectors = tuple(
            tuple(float(value) for value in vector)
            for vector in vectors
        )

        if not normalized_vectors:
            raise ValueError(
                "vectors must not be empty"
            )

        dimensions = len(normalized_vectors[0])

        if dimensions == 0:
            raise ValueError(
                "embedding vectors must not be empty"
            )

        for index, vector in enumerate(normalized_vectors):
            if len(vector) != dimensions:
                raise ValueError(
                    "all embedding vectors must have the same dimensions: "
                    f"invalid vector at index {index}"
                )

        return cls(
            model_name=normalized_model_name,
            model_version=normalized_model_version,
            dimensions=dimensions,
            vectors=normalized_vectors,
        )

    @property
    def count(self) -> int:
        """Return the number of vectors in the batch."""

        return len(self.vectors)

    @staticmethod
    def _require_non_empty_string(
        value: object,
        *,
        field_name: str,
    ) -> str:
        if not isinstance(value, str):
            raise TypeError(
                f"{field_name} must be a string"
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                f"{field_name} must not be empty"
            )

        return normalized


@runtime_checkable
class EmbeddingProvider(Protocol):
    """
    Port implemented by infrastructure-specific embedding providers.

    Implementations may call an external API, a local model, or a deterministic
    test double. The returned vector order must match the input text order.
    """

    async def embed(
        self,
        texts: Sequence[str],
    ) -> EmbeddingBatch:
        """
        Generate embeddings for an ordered sequence of texts.

        Raises:
            ValueError:
                If the input batch is empty or contains invalid text.
            EmbeddingProviderError:
                If the provider cannot generate embeddings.
        """

        ...


class EmbeddingProviderError(RuntimeError):
    """Raised when an embedding provider fails to generate vectors."""
