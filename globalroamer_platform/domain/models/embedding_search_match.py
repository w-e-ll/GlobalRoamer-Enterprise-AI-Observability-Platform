"""Domain model representing one semantic embedding search result."""

from __future__ import annotations

import math
from dataclasses import dataclass

from globalroamer_platform.domain.models.trace_chunk import (
    TraceChunk,
)


@dataclass(frozen=True, slots=True)
class EmbeddingSearchMatch:
    """
    Immutable semantic-search result for one trace chunk.

    The match exposes the trace chunk required by downstream application
    services together with provider-neutral similarity information.

    Infrastructure details such as SQLAlchemy models, pgvector expressions,
    and stored embedding vectors must not escape through this domain model.

    Similarity is normalized to the inclusive range [0.0, 1.0]:

    - 1.0 means maximum similarity
    - 0.0 means no similarity

    Distance is optional because some vector-search implementations may
    naturally return only a normalized similarity score. When supplied,
    distance must be a finite, non-negative number.
    """

    trace_chunk: TraceChunk
    similarity: float
    distance: float | None = None

    def __post_init__(self) -> None:
        self._validate_trace_chunk(
            self.trace_chunk,
        )
        self._validate_similarity(
            self.similarity,
        )
        self._validate_distance(
            self.distance,
        )

    @classmethod
    def create(
        cls,
        *,
        trace_chunk: TraceChunk,
        similarity: float,
        distance: float | None = None,
    ) -> EmbeddingSearchMatch:
        """
        Create and validate one semantic-search match.

        Numeric values are normalized to ``float`` while boolean values are
        rejected explicitly because ``bool`` is a subclass of ``int`` in
        Python.
        """

        return cls(
            trace_chunk=trace_chunk,
            similarity=cls._normalize_similarity(
                similarity,
            ),
            distance=cls._normalize_distance(
                distance,
            ),
        )

    @property
    def chunk_id(self):
        """Return the matched trace chunk identity."""

        return self.trace_chunk.id

    @property
    def tenant_id(self) -> str:
        """Return the tenant owning the matched trace chunk."""

        return self.trace_chunk.tenant_id

    @property
    def trace_id(self) -> str:
        """Return the trace owning the matched trace chunk."""

        return self.trace_chunk.trace_id

    @property
    def testcase_id(self) -> str | None:
        """Return the testcase associated with the matched trace chunk."""

        return self.trace_chunk.testcase_id

    @property
    def chunk_index(self) -> int:
        """Return the matched chunk's deterministic position in the trace."""

        return self.trace_chunk.chunk_index

    @property
    def text(self) -> str:
        """Return the matched trace chunk text."""

        return self.trace_chunk.text

    @staticmethod
    def _validate_trace_chunk(
        value: object,
    ) -> None:
        if not isinstance(value, TraceChunk):
            raise TypeError(
                "trace_chunk must be a TraceChunk"
            )

    @staticmethod
    def _validate_similarity(
        value: object,
    ) -> None:
        normalized = EmbeddingSearchMatch._normalize_similarity(
            value,
        )

        if normalized != value:
            raise ValueError(
                "similarity must already be normalized"
            )

    @staticmethod
    def _validate_distance(
        value: object,
    ) -> None:
        normalized = EmbeddingSearchMatch._normalize_distance(
            value,
        )

        if normalized != value:
            raise ValueError(
                "distance must already be normalized"
            )

    @staticmethod
    def _normalize_similarity(
        value: object,
    ) -> float:
        if isinstance(value, bool) or not isinstance(
            value,
            (
                int,
                float,
            ),
        ):
            raise TypeError(
                "similarity must be a number"
            )

        normalized = float(value)

        if not math.isfinite(normalized):
            raise ValueError(
                "similarity must be finite"
            )

        if normalized < 0.0 or normalized > 1.0:
            raise ValueError(
                "similarity must be between 0.0 and 1.0"
            )

        return normalized

    @staticmethod
    def _normalize_distance(
        value: object,
    ) -> float | None:
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(
            value,
            (
                int,
                float,
            ),
        ):
            raise TypeError(
                "distance must be a number or None"
            )

        normalized = float(value)

        if not math.isfinite(normalized):
            raise ValueError(
                "distance must be finite"
            )

        if normalized < 0.0:
            raise ValueError(
                "distance must be greater than or equal to zero"
            )

        return normalized
