"""Application port for semantic embedding search."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from globalroamer_platform.domain.models.embedding_search_match import (
    EmbeddingSearchMatch,
)


@runtime_checkable
class EmbeddingSearchRepository(Protocol):
    """
    Semantic-search abstraction over persisted embeddings.

    Implementations may use PostgreSQL with pgvector, Qdrant, Pinecone,
    Weaviate, Elasticsearch, or another vector-capable storage system.

    The application layer defines the search contract, while infrastructure
    is responsible for executing the similarity query and reconstructing
    domain-level search matches.

    Implementations must preserve tenant isolation and must never return
    chunks belonging to another tenant.
    """

    async def search_similar(
        self,
        *,
        tenant_id: str,
        query_embedding: tuple[float, ...],
        top_k: int,
        trace_id: str | None = None,
        testcase_id: str | None = None,
        model_name: str | None = None,
        model_version: str | None = None,
    ) -> tuple[EmbeddingSearchMatch, ...]:
        """
        Return the most semantically similar trace chunks.

        Args:
            tenant_id:
                Tenant scope used to enforce data isolation.
            query_embedding:
                Query vector produced by the configured embedding provider.
            top_k:
                Maximum number of matches to return.
            trace_id:
                Optional filter restricting results to one trace.
            testcase_id:
                Optional filter restricting results to one testcase.
            model_name:
                Optional filter restricting results to embeddings generated
                by one model.
            model_version:
                Optional filter restricting results to one model version.

        Returns:
            Matching chunks ordered by descending similarity. Results with
            equal similarity must use deterministic secondary ordering.

        Implementations may return fewer than ``top_k`` items when fewer
        eligible matches exist.

        Implementations should validate:

        - tenant_id is not empty
        - query_embedding is not empty
        - all embedding values are finite numbers
        - top_k is greater than zero
        - model_name and model_version are supplied together when model
          filtering is used
        """

        ...
