"""Tests for semantic trace-chunk retrieval."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

import pytest

from globalroamer_platform.application.ports.embedding_provider import (
    EmbeddingBatch,
    EmbeddingProviderError,
)
from globalroamer_platform.application.search.search_relevant_trace_chunks import (
    SearchRelevantTraceChunks,
    SearchRelevantTraceChunksCommand,
    SearchRelevantTraceChunksResult,
)
from globalroamer_platform.domain.models.embedding_search_match import (
    EmbeddingSearchMatch,
)
from globalroamer_platform.domain.models.trace_chunk import (
    TraceChunk,
)


class FakeEmbeddingProvider:
    """Configurable embedding provider test double."""

    def __init__(
        self,
        *,
        batch: EmbeddingBatch | None = None,
        error: Exception | None = None,
    ) -> None:
        self.batch = batch or EmbeddingBatch.create(
            model_name="test-model",
            model_version="1.0",
            vectors=(
                (
                    0.1,
                    0.2,
                    0.3,
                ),
            ),
        )
        self.error = error
        self.calls: list[tuple[str, ...]] = []

    async def embed(
        self,
        texts: Sequence[str],
    ) -> EmbeddingBatch:
        normalized_texts = tuple(texts)
        self.calls.append(normalized_texts)

        if self.error is not None:
            raise self.error

        return self.batch


class FakeEmbeddingSearchRepository:
    """Configurable semantic-search repository test double."""

    def __init__(
        self,
        *,
        matches: tuple[EmbeddingSearchMatch, ...] = (),
        error: Exception | None = None,
    ) -> None:
        self.matches = matches
        self.error = error
        self.calls: list[dict[str, object]] = []

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
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "query_embedding": query_embedding,
                "top_k": top_k,
                "trace_id": trace_id,
                "testcase_id": testcase_id,
                "model_name": model_name,
                "model_version": model_version,
            }
        )

        if self.error is not None:
            raise self.error

        return self.matches


def create_trace_chunk(
    *,
    tenant_id: str = "tenant-a",
    trace_id: str = "trace-001",
    testcase_id: str | None = "testcase-001",
    chunk_index: int = 0,
    text: str = "SIP registration failed with timeout.",
) -> TraceChunk:
    """Create a valid trace chunk for application tests."""

    return TraceChunk.create(
        tenant_id=tenant_id,
        trace_id=trace_id,
        testcase_id=testcase_id,
        chunk_index=chunk_index,
        text=text,
        event_ids=(
            uuid4(),
        ),
        event_names=(
            "sip.registration.failed",
        ),
        event_families=(
            "sip",
        ),
        severities=(
            "error",
        ),
        causes=(
            "timeout",
        ),
        tags=(
            "registration",
        ),
        has_failure=True,
        has_high_severity=True,
        has_retry_recommended=True,
    )


def create_match(
    *,
    tenant_id: str = "tenant-a",
    trace_id: str = "trace-001",
    testcase_id: str | None = "testcase-001",
    chunk_index: int = 0,
    similarity: float = 0.95,
    distance: float | None = 0.05,
) -> EmbeddingSearchMatch:
    """Create a valid semantic-search match."""

    chunk = create_trace_chunk(
        tenant_id=tenant_id,
        trace_id=trace_id,
        testcase_id=testcase_id,
        chunk_index=chunk_index,
        text=(
            "SIP registration failed with timeout "
            f"in chunk {chunk_index}."
        ),
    )

    return EmbeddingSearchMatch.create(
        trace_chunk=chunk,
        similarity=similarity,
        distance=distance,
    )


def test_command_create_normalizes_values() -> None:
    command = SearchRelevantTraceChunksCommand.create(
        tenant_id="  tenant-a  ",
        question="  Why did registration fail?  ",
        top_k=7,
        trace_id="  trace-001  ",
        testcase_id="  testcase-001  ",
    )

    assert command.tenant_id == "tenant-a"
    assert command.question == "Why did registration fail?"
    assert command.top_k == 7
    assert command.trace_id == "trace-001"
    assert command.testcase_id == "testcase-001"


def test_command_uses_default_top_k() -> None:
    command = SearchRelevantTraceChunksCommand.create(
        tenant_id="tenant-a",
        question="Why did registration fail?",
    )

    assert command.top_k == 5


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        (
            "tenant_id",
            "",
        ),
        (
            "tenant_id",
            "   ",
        ),
        (
            "question",
            "",
        ),
        (
            "question",
            "   ",
        ),
    ),
)
def test_command_rejects_empty_required_values(
    field_name: str,
    value: str,
) -> None:
    arguments = {
        "tenant_id": "tenant-a",
        "question": "Why did registration fail?",
    }
    arguments[field_name] = value

    with pytest.raises(
        ValueError,
        match=f"{field_name} must not be empty",
    ):
        SearchRelevantTraceChunksCommand.create(
            **arguments,
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        (
            "tenant_id",
            None,
        ),
        (
            "tenant_id",
            123,
        ),
        (
            "question",
            None,
        ),
        (
            "question",
            123,
        ),
    ),
)
def test_command_rejects_non_string_required_values(
    field_name: str,
    value: object,
) -> None:
    arguments = {
        "tenant_id": "tenant-a",
        "question": "Why did registration fail?",
    }
    arguments[field_name] = value

    with pytest.raises(
        TypeError,
        match=f"{field_name} must be a string",
    ):
        SearchRelevantTraceChunksCommand.create(
            **arguments,
        )


@pytest.mark.parametrize(
    "top_k",
    (
        0,
        -1,
        -100,
    ),
)
def test_command_rejects_non_positive_top_k(
    top_k: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="top_k must be greater than zero",
    ):
        SearchRelevantTraceChunksCommand.create(
            tenant_id="tenant-a",
            question="Why did registration fail?",
            top_k=top_k,
        )


@pytest.mark.parametrize(
    "top_k",
    (
        True,
        False,
        1.5,
        "5",
        None,
    ),
)
def test_command_rejects_non_integer_top_k(
    top_k: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="top_k must be an integer",
    ):
        SearchRelevantTraceChunksCommand.create(
            tenant_id="tenant-a",
            question="Why did registration fail?",
            top_k=top_k,
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "trace_id",
        "testcase_id",
    ),
)
def test_command_rejects_empty_optional_filter(
    field_name: str,
) -> None:
    arguments = {
        "tenant_id": "tenant-a",
        "question": "Why did registration fail?",
        field_name: "   ",
    }

    with pytest.raises(
        ValueError,
        match=f"{field_name} must not be empty",
    ):
        SearchRelevantTraceChunksCommand.create(
            **arguments,
        )


@pytest.mark.asyncio
async def test_execute_embeds_question_and_returns_matches() -> None:
    matches = (
        create_match(
            chunk_index=0,
            similarity=0.98,
            distance=0.02,
        ),
        create_match(
            chunk_index=1,
            similarity=0.91,
            distance=0.09,
        ),
    )

    provider = FakeEmbeddingProvider()
    repository = FakeEmbeddingSearchRepository(
        matches=matches,
    )
    use_case = SearchRelevantTraceChunks(
        embedding_provider=provider,
        search_repository=repository,
    )
    command = SearchRelevantTraceChunksCommand.create(
        tenant_id="tenant-a",
        question="Why did SIP registration fail?",
        top_k=5,
    )

    result = await use_case.execute(command)

    assert isinstance(
        result,
        SearchRelevantTraceChunksResult,
    )
    assert result.model_name == "test-model"
    assert result.model_version == "1.0"
    assert result.dimensions == 3
    assert result.matches == matches
    assert result.match_count == 2

    assert provider.calls == [
        (
            "Why did SIP registration fail?",
        ),
    ]


@pytest.mark.asyncio
async def test_execute_forwards_embedding_and_filters_to_repository() -> None:
    provider = FakeEmbeddingProvider(
        batch=EmbeddingBatch.create(
            model_name="sentence-transformers",
            model_version="all-MiniLM-L6-v2",
            vectors=(
                (
                    0.25,
                    0.50,
                    0.75,
                    1.00,
                ),
            ),
        )
    )
    repository = FakeEmbeddingSearchRepository()
    use_case = SearchRelevantTraceChunks(
        embedding_provider=provider,
        search_repository=repository,
    )
    command = SearchRelevantTraceChunksCommand.create(
        tenant_id="tenant-a",
        question="Find timeout failures",
        top_k=3,
        trace_id="trace-001",
        testcase_id="testcase-001",
    )

    await use_case.execute(command)

    assert repository.calls == [
        {
            "tenant_id": "tenant-a",
            "query_embedding": (
                0.25,
                0.50,
                0.75,
                1.00,
            ),
            "top_k": 3,
            "trace_id": "trace-001",
            "testcase_id": "testcase-001",
            "model_name": "sentence-transformers",
            "model_version": "all-MiniLM-L6-v2",
        }
    ]


@pytest.mark.asyncio
async def test_execute_returns_empty_result_when_no_matches_exist() -> None:
    provider = FakeEmbeddingProvider()
    repository = FakeEmbeddingSearchRepository(
        matches=(),
    )
    use_case = SearchRelevantTraceChunks(
        embedding_provider=provider,
        search_repository=repository,
    )

    result = await use_case.execute(
        SearchRelevantTraceChunksCommand.create(
            tenant_id="tenant-a",
            question="Find an unknown failure",
        )
    )

    assert result.matches == ()
    assert result.match_count == 0


@pytest.mark.asyncio
async def test_execute_propagates_embedding_provider_error() -> None:
    provider_error = EmbeddingProviderError(
        "embedding provider unavailable"
    )
    provider = FakeEmbeddingProvider(
        error=provider_error,
    )
    repository = FakeEmbeddingSearchRepository()
    use_case = SearchRelevantTraceChunks(
        embedding_provider=provider,
        search_repository=repository,
    )

    with pytest.raises(
        EmbeddingProviderError,
        match="embedding provider unavailable",
    ):
        await use_case.execute(
            SearchRelevantTraceChunksCommand.create(
                tenant_id="tenant-a",
                question="Why did registration fail?",
            )
        )

    assert repository.calls == []


@pytest.mark.asyncio
async def test_execute_propagates_repository_error() -> None:
    repository_error = RuntimeError(
        "vector search unavailable"
    )
    provider = FakeEmbeddingProvider()
    repository = FakeEmbeddingSearchRepository(
        error=repository_error,
    )
    use_case = SearchRelevantTraceChunks(
        embedding_provider=provider,
        search_repository=repository,
    )

    with pytest.raises(
        RuntimeError,
        match="vector search unavailable",
    ):
        await use_case.execute(
            SearchRelevantTraceChunksCommand.create(
                tenant_id="tenant-a",
                question="Why did registration fail?",
            )
        )


@pytest.mark.asyncio
async def test_execute_rejects_provider_returning_multiple_vectors() -> None:
    provider = FakeEmbeddingProvider(
        batch=EmbeddingBatch.create(
            model_name="test-model",
            model_version="1.0",
            vectors=(
                (
                    0.1,
                    0.2,
                ),
                (
                    0.3,
                    0.4,
                ),
            ),
        )
    )
    repository = FakeEmbeddingSearchRepository()
    use_case = SearchRelevantTraceChunks(
        embedding_provider=provider,
        search_repository=repository,
    )

    with pytest.raises(
        ValueError,
        match=(
            "embedding provider must return exactly one "
            "vector"
        ),
    ):
        await use_case.execute(
            SearchRelevantTraceChunksCommand.create(
                tenant_id="tenant-a",
                question="Why did registration fail?",
            )
        )

    assert repository.calls == []


@pytest.mark.asyncio
async def test_execute_rejects_inconsistent_embedding_dimensions() -> None:
    invalid_batch = EmbeddingBatch(
        model_name="test-model",
        model_version="1.0",
        dimensions=4,
        vectors=(
            (
                0.1,
                0.2,
                0.3,
            ),
        ),
    )
    provider = FakeEmbeddingProvider(
        batch=invalid_batch,
    )
    repository = FakeEmbeddingSearchRepository()
    use_case = SearchRelevantTraceChunks(
        embedding_provider=provider,
        search_repository=repository,
    )

    with pytest.raises(
        ValueError,
        match=(
            "query embedding dimensions do not match "
            "the embedding batch dimensions"
        ),
    ):
        await use_case.execute(
            SearchRelevantTraceChunksCommand.create(
                tenant_id="tenant-a",
                question="Why did registration fail?",
            )
        )

    assert repository.calls == []


@pytest.mark.asyncio
async def test_execute_rejects_more_matches_than_top_k() -> None:
    matches = (
        create_match(
            chunk_index=0,
        ),
        create_match(
            chunk_index=1,
        ),
    )
    provider = FakeEmbeddingProvider()
    repository = FakeEmbeddingSearchRepository(
        matches=matches,
    )
    use_case = SearchRelevantTraceChunks(
        embedding_provider=provider,
        search_repository=repository,
    )

    with pytest.raises(
        ValueError,
        match=(
            "search repository returned more matches "
            "than requested by top_k"
        ),
    ):
        await use_case.execute(
            SearchRelevantTraceChunksCommand.create(
                tenant_id="tenant-a",
                question="Why did registration fail?",
                top_k=1,
            )
        )


@pytest.mark.asyncio
async def test_execute_rejects_match_from_another_tenant() -> None:
    provider = FakeEmbeddingProvider()
    repository = FakeEmbeddingSearchRepository(
        matches=(
            create_match(
                tenant_id="tenant-b",
            ),
        )
    )
    use_case = SearchRelevantTraceChunks(
        embedding_provider=provider,
        search_repository=repository,
    )

    with pytest.raises(
        ValueError,
        match=(
            "search repository returned a match "
            "belonging to another tenant"
        ),
    ):
        await use_case.execute(
            SearchRelevantTraceChunksCommand.create(
                tenant_id="tenant-a",
                question="Why did registration fail?",
            )
        )


@pytest.mark.asyncio
async def test_execute_rejects_match_outside_requested_trace() -> None:
    provider = FakeEmbeddingProvider()
    repository = FakeEmbeddingSearchRepository(
        matches=(
            create_match(
                trace_id="trace-002",
            ),
        )
    )
    use_case = SearchRelevantTraceChunks(
        embedding_provider=provider,
        search_repository=repository,
    )

    with pytest.raises(
        ValueError,
        match=(
            "search repository returned a match "
            "outside the requested trace"
        ),
    ):
        await use_case.execute(
            SearchRelevantTraceChunksCommand.create(
                tenant_id="tenant-a",
                question="Why did registration fail?",
                trace_id="trace-001",
            )
        )


@pytest.mark.asyncio
async def test_execute_rejects_match_outside_requested_testcase() -> None:
    provider = FakeEmbeddingProvider()
    repository = FakeEmbeddingSearchRepository(
        matches=(
            create_match(
                testcase_id="testcase-002",
            ),
        )
    )
    use_case = SearchRelevantTraceChunks(
        embedding_provider=provider,
        search_repository=repository,
    )

    with pytest.raises(
        ValueError,
        match=(
            "search repository returned a match "
            "outside the requested testcase"
        ),
    ):
        await use_case.execute(
            SearchRelevantTraceChunksCommand.create(
                tenant_id="tenant-a",
                question="Why did registration fail?",
                testcase_id="testcase-001",
            )
        )


@pytest.mark.asyncio
async def test_execute_rejects_non_match_repository_item() -> None:
    provider = FakeEmbeddingProvider()
    repository = FakeEmbeddingSearchRepository()

    repository.matches = (
        "invalid-match",
    )

    use_case = SearchRelevantTraceChunks(
        embedding_provider=provider,
        search_repository=repository,
    )

    with pytest.raises(
        TypeError,
        match=(
            "search repository must return only "
            "EmbeddingSearchMatch instances"
        ),
    ):
        await use_case.execute(
            SearchRelevantTraceChunksCommand.create(
                tenant_id="tenant-a",
                question="Why did registration fail?",
            )
        )


@pytest.mark.asyncio
async def test_execute_rejects_invalid_command_type() -> None:
    provider = FakeEmbeddingProvider()
    repository = FakeEmbeddingSearchRepository()
    use_case = SearchRelevantTraceChunks(
        embedding_provider=provider,
        search_repository=repository,
    )

    with pytest.raises(
        TypeError,
        match=(
            "command must be a "
            "SearchRelevantTraceChunksCommand"
        ),
    ):
        await use_case.execute(
            "invalid-command",
        )

    assert provider.calls == []
    assert repository.calls == []
