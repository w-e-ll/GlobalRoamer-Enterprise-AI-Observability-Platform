"""Worker responsible for generating embeddings for persisted trace chunks.

The worker accepts a TRACE_CHUNKED event, reloads the authoritative
TraceChunk objects through the EmbedTraceChunks application use case,
generates and persists embedding records, creates an
EMBEDDINGS_GENERATED event, and stores that event in the transactional
outbox.

The worker does not commit or roll back the database transaction.
Transaction ownership belongs to the infrastructure runtime.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from globalroamer_platform.application.embeddings.embed_trace_chunks import (
    EmbedTraceChunks,
    EmbedTraceChunksCommand,
    EmbedTraceChunksResult,
)
from globalroamer_platform.application.ports.outbox_repository import (
    OutboxRepository,
)
from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    EMBEDDINGS_GENERATED,
    TRACE_CHUNKED,
)


logger = logging.getLogger(__name__)


class EmbeddingWorker:
    """
    Generate embeddings for persisted trace chunks.

    Embedding records and the outgoing outbox message are written inside
    the transaction controlled by the runtime caller.
    """

    PRODUCER = "globalroamer.embedding-worker"

    def __init__(
        self,
        *,
        embed_trace_chunks: EmbedTraceChunks,
        outbox_repository: OutboxRepository,
    ) -> None:
        if not isinstance(
            embed_trace_chunks,
            EmbedTraceChunks,
        ):
            raise TypeError(
                "embed_trace_chunks must be an EmbedTraceChunks"
            )

        self._embed_trace_chunks = embed_trace_chunks
        self._outbox_repository = outbox_repository

    async def handle(
        self,
        event: EventEnvelope,
    ) -> EventEnvelope:
        """
        Process one TRACE_CHUNKED event.

        Returns:
            The EMBEDDINGS_GENERATED event stored in the transactional
            outbox.

        Raises:
            TypeError: When the incoming object has an invalid type.
            ValueError: When the event type or payload is invalid.
            Exception: Propagates application or infrastructure failures
                so the runtime can roll back and retry.
        """
        self._validate_event_type(event)

        command = self._to_command(event)

        logger.info(
            "Embedding worker started",
            extra={
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "correlation_id": event.correlation_id,
                "tenant_id": command.tenant_id,
                "trace_id": command.trace_id,
                "batch_size": command.batch_size,
                "stage": "worker.embedding",
            },
        )

        try:
            result = await self._embed_trace_chunks.execute(
                command
            )

            outgoing_event = self._to_embeddings_generated_event(
                source_event=event,
                result=result,
            )

            outbox_message = OutboxMessage.create(
                event=outgoing_event,
            )

            await self._outbox_repository.add(
                outbox_message
            )

        except Exception as exc:
            logger.exception(
                "Embedding worker failed",
                extra={
                    "event_id": str(event.event_id),
                    "event_type": event.event_type,
                    "correlation_id": event.correlation_id,
                    "tenant_id": command.tenant_id,
                    "trace_id": command.trace_id,
                    "batch_size": command.batch_size,
                    "stage": "worker.embedding",
                    "error_type": type(exc).__name__,
                },
            )
            raise

        logger.info(
            "Embedding worker completed",
            extra={
                "event_id": str(event.event_id),
                "produced_event_id": str(
                    outgoing_event.event_id
                ),
                "outbox_message_id": str(
                    outbox_message.id
                ),
                "correlation_id": event.correlation_id,
                "tenant_id": result.tenant_id,
                "trace_id": result.trace_id,
                "model_name": result.model_name,
                "model_version": result.model_version,
                "dimensions": result.dimensions,
                "chunk_count": result.chunk_count,
                "embedding_count": result.embedding_count,
                "stage": "worker.embedding",
            },
        )

        return outgoing_event

    @staticmethod
    def _validate_event_type(
        event: EventEnvelope,
    ) -> None:
        """Ensure the worker received a supported event type."""
        if not isinstance(
            event,
            EventEnvelope,
        ):
            raise TypeError(
                "event must be an EventEnvelope"
            )

        if event.event_type != TRACE_CHUNKED:
            raise ValueError(
                "EmbeddingWorker supports only "
                f"{TRACE_CHUNKED!r} events; "
                f"received {event.event_type!r}"
            )

    @classmethod
    def _to_command(
        cls,
        event: EventEnvelope,
    ) -> EmbedTraceChunksCommand:
        """Convert the incoming event into an embedding command."""
        trace_id = cls._required_string(
            event.payload,
            "trace_id",
        )

        batch_size = cls._optional_positive_integer(
            event.payload,
            "embedding_batch_size",
            default=32,
        )

        return EmbedTraceChunksCommand(
            tenant_id=event.tenant_id,
            trace_id=trace_id,
            batch_size=batch_size,
        )

    @classmethod
    def _to_embeddings_generated_event(
        cls,
        *,
        source_event: EventEnvelope,
        result: EmbedTraceChunksResult,
    ) -> EventEnvelope:
        """
        Create the EMBEDDINGS_GENERATED event produced by this worker.

        Embedding vectors are intentionally excluded from the event payload.
        PostgreSQL remains authoritative for the generated embedding records.
        The event contains identity, model metadata, counts, and record IDs.
        """
        payload: dict[str, Any] = {
            "trace_id": result.trace_id,
            "model_name": result.model_name,
            "model_version": result.model_version,
            "dimensions": result.dimensions,
            "chunk_count": result.chunk_count,
            "embedding_count": result.embedding_count,
            "embedding_ids": [
                str(embedding_id)
                for embedding_id in result.embedding_ids
            ],
        }

        return EventEnvelope(
            event_id=uuid4(),
            event_type=EMBEDDINGS_GENERATED,
            event_version=1,
            correlation_id=source_event.correlation_id,
            causation_id=source_event.event_id,
            tenant_id=result.tenant_id,
            occurred_at=datetime.now(
                timezone.utc
            ),
            producer=cls.PRODUCER,
            payload=payload,
        )

    @staticmethod
    def _required_string(
        payload: dict[str, Any],
        field_name: str,
    ) -> str:
        """Read and validate one required string payload field."""
        value = payload.get(field_name)

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise ValueError(
                "Event payload must contain a "
                f"non-empty {field_name!r} string"
            )

        return value.strip()

    @staticmethod
    def _optional_positive_integer(
        payload: dict[str, Any],
        field_name: str,
        *,
        default: int,
    ) -> int:
        """Read an optional positive integer payload field."""
        value = payload.get(
            field_name,
            default,
        )

        if isinstance(value, bool):
            raise ValueError(
                "Event payload field "
                f"{field_name!r} must be a positive integer"
            )

        if not isinstance(value, int):
            raise ValueError(
                "Event payload field "
                f"{field_name!r} must be a positive integer"
            )

        if value <= 0:
            raise ValueError(
                "Event payload field "
                f"{field_name!r} must be greater than zero"
            )

        return value
