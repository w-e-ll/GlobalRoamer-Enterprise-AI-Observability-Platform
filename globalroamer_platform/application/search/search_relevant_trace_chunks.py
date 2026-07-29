"""Application use case for semantic trace-chunk retrieval."""

from __future__ import annotations

from dataclasses import dataclass

from globalroamer_platform.application.ports.embedding_provider import (
    EmbeddingProvider,
)
from globalroamer_platform.application.ports.embedding_search_repository import (
    EmbeddingSearchRepository,
)
from globalroamer_platform.domain.models.embedding_search_match import (
    EmbeddingSearchMatch,
)


@dataclass(frozen=True, slots=True)
class SearchRelevantTraceChunksCommand:
    """
    Request to find trace chunks relevant to a natural-language question.

    Search is always scoped to one tenant. It may optionally be restricted
    to one trace or testcase.
    """

    tenant_id: str
    question: str
    top_k: int = 5
    trace_id: str | None = None
    testcase_id: str | None = None

    def __post_init__(self) -> None:
        self._validate_required_string(
            self.tenant_id,
            field_name="tenant_id",
        )
        self._validate_required_string(
            self.question,
            field_name="question",
        )
        self._validate_optional_string(
            self.trace_id,
            field_name="trace_id",
        )
        self._validate_optional_string(
            self.testcase_id,
            field_name="testcase_id",
        )
        self._validate_top_k(
            self.top_k,
        )

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        question: str,
        top_k: int = 5,
        trace_id: str | None = None,
        testcase_id: str | None = None,
    ) -> SearchRelevantTraceChunksCommand:
        """Create a normalized semantic-search command."""

        return cls(
            tenant_id=cls._normalize_required_string(
                tenant_id,
                field_name="tenant_id",
            ),
            question=cls._normalize_required_string(
                question,
                field_name="question",
            ),
            top_k=top_k,
            trace_id=cls._normalize_optional_string(
                trace_id,
                field_name="trace_id",
            ),
            testcase_id=cls._normalize_optional_string(
                testcase_id,
                field_name="testcase_id",
            ),
        )

    @staticmethod
    def _normalize_required_string(
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

    @classmethod
    def _normalize_optional_string(
        cls,
        value: object,
        *,
        field_name: str,
    ) -> str | None:
        if value is None:
            return None

        return cls._normalize_required_string(
            value,
            field_name=field_name,
        )

    @classmethod
    def _validate_required_string(
        cls,
        value: object,
        *,
        field_name: str,
    ) -> None:
        normalized = cls._normalize_required_string(
            value,
            field_name=field_name,
        )

        if normalized != value:
            raise ValueError(
                f"{field_name} must already be normalized"
            )

    @classmethod
    def _validate_optional_string(
        cls,
        value: object,
        *,
        field_name: str,
    ) -> None:
        normalized = cls._normalize_optional_string(
            value,
            field_name=field_name,
        )

        if normalized != value:
            raise ValueError(
                f"{field_name} must already be normalized"
            )

    @staticmethod
    def _validate_top_k(
        value: object,
    ) -> None:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
        ):
            raise TypeError(
                "top_k must be an integer"
            )

        if value <= 0:
            raise ValueError(
                "top_k must be greater than zero"
            )


@dataclass(frozen=True, slots=True)
class SearchRelevantTraceChunksResult:
    """
    Result returned by semantic trace-chunk retrieval.

    Model identity and vector dimensions describe the embedding used for the
    query. Matches are returned in repository-defined relevance order.
    """

    model_name: str
    model_version: str
    dimensions: int
    matches: tuple[EmbeddingSearchMatch, ...]

    def __post_init__(self) -> None:
        self._validate_required_string(
            self.model_name,
            field_name="model_name",
        )
        self._validate_required_string(
            self.model_version,
            field_name="model_version",
        )

        if (
            not isinstance(self.dimensions, int)
            or isinstance(self.dimensions, bool)
        ):
            raise TypeError(
                "dimensions must be an integer"
            )

        if self.dimensions <= 0:
            raise ValueError(
                "dimensions must be greater than zero"
            )

        if not isinstance(self.matches, tuple):
            raise TypeError(
                "matches must be a tuple"
            )

        for index, match in enumerate(self.matches):
            if not isinstance(
                match,
                EmbeddingSearchMatch,
            ):
                raise TypeError(
                    "matches must contain only "
                    "EmbeddingSearchMatch instances: "
                    f"invalid item at index {index}"
                )

    @property
    def match_count(self) -> int:
        """Return the number of retrieved matches."""

        return len(self.matches)

    @staticmethod
    def _validate_required_string(
        value: object,
        *,
        field_name: str,
    ) -> None:
        if not isinstance(value, str):
            raise TypeError(
                f"{field_name} must be a string"
            )

        if not value:
            raise ValueError(
                f"{field_name} must not be empty"
            )

        if value != value.strip():
            raise ValueError(
                f"{field_name} must already be normalized"
            )


class SearchRelevantTraceChunks:
    """
    Generate a query embedding and retrieve semantically similar chunks.

    The use case coordinates application ports only. It has no knowledge of
    SQLAlchemy, PostgreSQL, pgvector, HTTP APIs, or provider-specific clients.
    """

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        search_repository: EmbeddingSearchRepository,
    ) -> None:
        if not isinstance(
            embedding_provider,
            EmbeddingProvider,
        ):
            raise TypeError(
                "embedding_provider must implement "
                "EmbeddingProvider"
            )

        if not isinstance(
            search_repository,
            EmbeddingSearchRepository,
        ):
            raise TypeError(
                "search_repository must implement "
                "EmbeddingSearchRepository"
            )

        self._embedding_provider = embedding_provider
        self._search_repository = search_repository

    async def execute(
        self,
        command: SearchRelevantTraceChunksCommand,
    ) -> SearchRelevantTraceChunksResult:
        """
        Find chunks semantically relevant to the supplied question.

        The question is embedded as a single-item batch. The embedding
        provider's model identity is forwarded to the search repository so
        stored vectors from incompatible models are not compared.
        """

        if not isinstance(
            command,
            SearchRelevantTraceChunksCommand,
        ):
            raise TypeError(
                "command must be a "
                "SearchRelevantTraceChunksCommand"
            )

        embedding_batch = await self._embedding_provider.embed(
            (
                command.question,
            ),
        )

        if embedding_batch.count != 1:
            raise ValueError(
                "embedding provider must return exactly one "
                "vector for one search question"
            )

        query_embedding = embedding_batch.vectors[0]

        if len(query_embedding) != embedding_batch.dimensions:
            raise ValueError(
                "query embedding dimensions do not match "
                "the embedding batch dimensions"
            )

        matches = await self._search_repository.search_similar(
            tenant_id=command.tenant_id,
            query_embedding=query_embedding,
            top_k=command.top_k,
            trace_id=command.trace_id,
            testcase_id=command.testcase_id,
            model_name=embedding_batch.model_name,
            model_version=embedding_batch.model_version,
        )

        normalized_matches = tuple(matches)

        if len(normalized_matches) > command.top_k:
            raise ValueError(
                "search repository returned more matches "
                "than requested by top_k"
            )

        for index, match in enumerate(normalized_matches):
            if not isinstance(
                match,
                EmbeddingSearchMatch,
            ):
                raise TypeError(
                    "search repository must return only "
                    "EmbeddingSearchMatch instances: "
                    f"invalid item at index {index}"
                )

            if match.tenant_id != command.tenant_id:
                raise ValueError(
                    "search repository returned a match "
                    "belonging to another tenant"
                )

            if (
                command.trace_id is not None
                and match.trace_id != command.trace_id
            ):
                raise ValueError(
                    "search repository returned a match "
                    "outside the requested trace"
                )

            if (
                command.testcase_id is not None
                and match.testcase_id
                != command.testcase_id
            ):
                raise ValueError(
                    "search repository returned a match "
                    "outside the requested testcase"
                )

        return SearchRelevantTraceChunksResult(
            model_name=embedding_batch.model_name,
            model_version=embedding_batch.model_version,
            dimensions=embedding_batch.dimensions,
            matches=normalized_matches,
        )
