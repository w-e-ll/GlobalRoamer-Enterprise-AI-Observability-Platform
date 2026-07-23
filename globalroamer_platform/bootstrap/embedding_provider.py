"""Composition root for the production embedding provider."""

from __future__ import annotations

from globalroamer_platform.application.ports.embedding_provider import (
    EmbeddingProvider,
)
from globalroamer_platform.infrastructure.embeddings.sentence_transformer_embedding_provider import (
    SentenceTransformerEmbeddingProvider,
)


_DEFAULT_MODEL_VERSION = "1.0.0"
_DEFAULT_BATCH_SIZE = 32


def build_embedding_provider(
    *,
    model_name: str,
    model_version: str = _DEFAULT_MODEL_VERSION,
    device: str | None = None,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    normalize_embeddings: bool = True,
    trust_remote_code: bool = False,
) -> EmbeddingProvider:
    """
    Build the production embedding provider.

    The returned provider implements the application EmbeddingProvider
    port using a locally hosted Sentence Transformers model.

    Args:
        model_name:
            Hugging Face model identifier or local model directory.

        model_version:
            Stable version persisted together with generated embeddings.

        device:
            Optional execution device such as ``cpu``, ``cuda`` or ``mps``.
            When omitted, Sentence Transformers selects the best available
            execution device automatically.

        batch_size:
            Number of texts encoded during one inference batch.

        normalize_embeddings:
            Whether embeddings should be L2-normalized before persistence.

        trust_remote_code:
            Whether Hugging Face repositories may execute custom code while
            loading the model.

    Returns:
        Configured EmbeddingProvider implementation.
    """

    return SentenceTransformerEmbeddingProvider(
        model_name=model_name,
        model_version=model_version,
        device=device,
        batch_size=batch_size,
        normalize_embeddings=normalize_embeddings,
        trust_remote_code=trust_remote_code,
    )
