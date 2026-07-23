"""Sentence Transformers implementation of the embedding provider port."""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable, Sequence
from typing import Any

from globalroamer_platform.application.ports.embedding_provider import (
    EmbeddingBatch,
    EmbeddingProviderError,
)


logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 32
_DEFAULT_MODEL_VERSION = "default"


class SentenceTransformerEmbeddingProvider:
    """
    Generate dense embeddings with a local Sentence Transformers model.

    Model loading is performed during provider construction. Encoding is
    delegated to a worker thread because SentenceTransformer.encode() is a
    synchronous, CPU/GPU-bound operation and must not block the application's
    asyncio event loop.

    A provider-level lock serializes calls against the same model instance.
    This avoids concurrent access to model state while still allowing the rest
    of the event-driven runtime to remain asynchronous.
    """

    def __init__(
        self,
        *,
        model_name: str,
        model_version: str = _DEFAULT_MODEL_VERSION,
        device: str | None = None,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        normalize_embeddings: bool = True,
        trust_remote_code: bool = False,
        model_factory: Callable[..., Any] | None = None,
    ) -> None:
        """Initialize and load the configured Sentence Transformers model."""
        self._model_name = self._require_non_empty_string(
            model_name,
            field_name="model_name",
        )
        self._model_version = self._require_non_empty_string(
            model_version,
            field_name="model_version",
        )
        self._device = self._normalize_optional_string(
            device,
            field_name="device",
        )
        self._batch_size = self._validate_batch_size(batch_size)

        if not isinstance(normalize_embeddings, bool):
            raise TypeError("normalize_embeddings must be a boolean")

        if not isinstance(trust_remote_code, bool):
            raise TypeError("trust_remote_code must be a boolean")

        self._normalize_embeddings = normalize_embeddings
        self._encode_lock = asyncio.Lock()

        factory = model_factory or self._load_sentence_transformer_class()

        model_kwargs: dict[str, object] = {
            "trust_remote_code": trust_remote_code,
        }
        if self._device is not None:
            model_kwargs["device"] = self._device

        try:
            self._model = factory(
                self._model_name,
                **model_kwargs,
            )
        except Exception as exc:
            raise EmbeddingProviderError(
                "failed to load Sentence Transformers model "
                f"{self._model_name!r}"
            ) from exc

        self._dimensions = self._resolve_dimensions(self._model)

        logger.info(
            "Sentence Transformers embedding provider initialized "
            "model_name=%s model_version=%s dimensions=%s "
            "device=%s batch_size=%s normalize_embeddings=%s",
            self._model_name,
            self._model_version,
            self._dimensions,
            self._device or "auto",
            self._batch_size,
            self._normalize_embeddings,
        )

    async def embed(
        self,
        texts: Sequence[str],
    ) -> EmbeddingBatch:
        """Generate embeddings while preserving input order."""
        normalized_texts = self._validate_texts(texts)

        try:
            async with self._encode_lock:
                raw_vectors = await asyncio.to_thread(
                    self._encode,
                    normalized_texts,
                )

            vectors = self._normalize_vectors(
                raw_vectors=raw_vectors,
                expected_count=len(normalized_texts),
                expected_dimensions=self._dimensions,
            )

            return EmbeddingBatch.create(
                model_name=self._model_name,
                model_version=self._model_version,
                vectors=vectors,
            )
        except (TypeError, ValueError):
            raise
        except EmbeddingProviderError:
            raise
        except Exception as exc:
            raise EmbeddingProviderError(
                "Sentence Transformers model failed to generate embeddings "
                f"for {len(normalized_texts)} texts"
            ) from exc

    def _encode(
        self,
        texts: tuple[str, ...],
    ) -> object:
        """Execute synchronous model inference in a worker thread."""
        try:
            return self._model.encode(
                list(texts),
                batch_size=self._batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=self._normalize_embeddings,
            )
        except Exception as exc:
            raise EmbeddingProviderError(
                "Sentence Transformers inference failed "
                f"for model {self._model_name!r}"
            ) from exc

    @staticmethod
    def _load_sentence_transformer_class() -> Callable[..., Any]:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingProviderError(
                "sentence-transformers is not installed; install the "
                "'sentence-transformers' package to use this provider"
            ) from exc

        return SentenceTransformer

    @staticmethod
    def _resolve_dimensions(model: object) -> int:
        dimension_getter = getattr(
            model,
            "get_sentence_embedding_dimension",
            None,
        )

        if not callable(dimension_getter):
            raise EmbeddingProviderError(
                "Sentence Transformers model does not expose "
                "get_sentence_embedding_dimension()"
            )

        try:
            dimensions = dimension_getter()
        except Exception as exc:
            raise EmbeddingProviderError(
                "failed to determine model embedding dimensions"
            ) from exc

        if (
            isinstance(dimensions, bool)
            or not isinstance(dimensions, int)
            or dimensions <= 0
        ):
            raise EmbeddingProviderError(
                "Sentence Transformers model returned invalid embedding "
                f"dimensions: {dimensions!r}"
            )

        return dimensions

    @classmethod
    def _normalize_vectors(
        cls,
        *,
        raw_vectors: object,
        expected_count: int,
        expected_dimensions: int,
    ) -> tuple[tuple[float, ...], ...]:
        try:
            if hasattr(raw_vectors, "tolist"):
                raw_vectors = raw_vectors.tolist()

            vectors = tuple(
                tuple(
                    cls._finite_float(
                        value,
                        vector_index=vector_index,
                        dimension_index=dimension_index,
                    )
                    for dimension_index, value in enumerate(vector)
                )
                for vector_index, vector in enumerate(raw_vectors)  # type: ignore[arg-type]
            )
        except EmbeddingProviderError:
            raise
        except (TypeError, ValueError) as exc:
            raise EmbeddingProviderError(
                "Sentence Transformers returned malformed embedding vectors"
            ) from exc

        if len(vectors) != expected_count:
            raise EmbeddingProviderError(
                "Sentence Transformers returned an unexpected vector count: "
                f"expected={expected_count} actual={len(vectors)}"
            )

        for index, vector in enumerate(vectors):
            if len(vector) != expected_dimensions:
                raise EmbeddingProviderError(
                    "Sentence Transformers returned an unexpected vector "
                    f"dimension at index {index}: "
                    f"expected={expected_dimensions} actual={len(vector)}"
                )

        return vectors

    @staticmethod
    def _finite_float(
        value: object,
        *,
        vector_index: int,
        dimension_index: int,
    ) -> float:
        try:
            normalized = float(value)
        except (TypeError, ValueError) as exc:
            raise EmbeddingProviderError(
                "embedding vector contains a non-numeric value at "
                f"vector={vector_index} dimension={dimension_index}"
            ) from exc

        if not math.isfinite(normalized):
            raise EmbeddingProviderError(
                "embedding vector contains a non-finite value at "
                f"vector={vector_index} dimension={dimension_index}"
            )

        return normalized

    @classmethod
    def _validate_texts(
        cls,
        texts: Sequence[str],
    ) -> tuple[str, ...]:
        if isinstance(texts, (str, bytes)):
            raise TypeError(
                "texts must be a sequence of strings, not a single string"
            )

        if not isinstance(texts, Sequence):
            raise TypeError("texts must be a sequence of strings")

        if not texts:
            raise ValueError("texts must not be empty")

        return tuple(
            cls._require_non_empty_string(
                text,
                field_name=f"texts[{index}]",
            )
            for index, text in enumerate(texts)
        )

    @staticmethod
    def _validate_batch_size(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("batch_size must be an integer")

        if value <= 0:
            raise ValueError("batch_size must be greater than zero")

        return value

    @staticmethod
    def _normalize_optional_string(
        value: object,
        *,
        field_name: str,
    ) -> str | None:
        if value is None:
            return None

        return SentenceTransformerEmbeddingProvider._require_non_empty_string(
            value,
            field_name=field_name,
        )

    @staticmethod
    def _require_non_empty_string(
        value: object,
        *,
        field_name: str,
    ) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")

        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} must not be empty")

        return normalized
