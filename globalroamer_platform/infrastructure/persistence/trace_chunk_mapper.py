from __future__ import annotations

from uuid import UUID

from globalroamer_platform.domain.models.trace_chunk import (
    TraceChunk,
)
from globalroamer_platform.infrastructure.database.models import (
    TraceChunkModel,
)


class TraceChunkMapper:
    """
    Maps TraceChunk domain objects to and from SQLAlchemy models.

    Persistence-specific representations such as JSON-compatible UUID strings
    are isolated here and do not leak into the domain layer.
    """

    @staticmethod
    def to_model(chunk: TraceChunk) -> TraceChunkModel:
        if not isinstance(chunk, TraceChunk):
            raise TypeError(
                "chunk must be a TraceChunk"
            )

        return TraceChunkModel(
            id=chunk.id,
            tenant_id=chunk.tenant_id,
            trace_id=chunk.trace_id,
            testcase_id=chunk.testcase_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            event_ids=[
                str(event_id)
                for event_id in chunk.event_ids
            ],
            event_count=chunk.event_count,
            event_names=list(chunk.event_names),
            event_families=list(chunk.event_families),
            severities=list(chunk.severities),
            causes=list(chunk.causes),
            tags=list(chunk.tags),
            has_failure=chunk.has_failure,
            has_high_severity=chunk.has_high_severity,
            has_retry_recommended=(
                chunk.has_retry_recommended
            ),
            created_at=chunk.created_at,
            content_hash=chunk.content_hash,
        )

    @staticmethod
    def to_domain(model: TraceChunkModel) -> TraceChunk:
        if not isinstance(model, TraceChunkModel):
            raise TypeError(
                "model must be a TraceChunkModel"
            )

        return TraceChunk(
            id=model.id,
            tenant_id=model.tenant_id,
            trace_id=model.trace_id,
            testcase_id=model.testcase_id,
            chunk_index=model.chunk_index,
            text=model.text,
            event_ids=tuple(
                UUID(event_id)
                for event_id in model.event_ids
            ),
            event_count=model.event_count,
            event_names=tuple(model.event_names),
            event_families=tuple(
                model.event_families
            ),
            severities=tuple(model.severities),
            causes=tuple(model.causes),
            tags=tuple(model.tags),
            has_failure=model.has_failure,
            has_high_severity=(
                model.has_high_severity
            ),
            has_retry_recommended=(
                model.has_retry_recommended
            ),
            created_at=model.created_at,
            content_hash=model.content_hash,
        )
