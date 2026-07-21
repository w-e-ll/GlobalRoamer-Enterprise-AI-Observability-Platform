"""Worker responsible for chunking persisted operational events.

The worker accepts a TRACE_NORMALIZED event, reloads the authoritative
OperationalEvent objects from PostgreSQL, invokes the ChunkTrace
application use case, replaces persisted TraceChunk objects, creates a
TRACE_CHUNKED event, and stores that event in the transactional outbox.

The worker does not commit or roll back the database transaction.
Transaction ownership belongs to the infrastructure runtime.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from globalroamer_platform.application.ports.outbox_repository import (
    OutboxRepository,
)
from globalroamer_platform.application.traces.chunk_trace import (
    ChunkTrace,
    ChunkTraceCommand,
    ChunkTraceResult,
)
from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_CHUNKED,
    TRACE_NORMALIZED,
)
from globalroamer_platform.infrastructure.persistence.operational_event_store import (
    OperationalEventStore,
)
from globalroamer_platform.infrastructure.persistence.trace_chunk_store import (
    TraceChunkStore,
)


logger = logging.getLogger(__name__)


class ChunkWorker:
    """
    Chunk persisted operational events and enqueue an outgoing event.

    Operational events, trace chunks, and the outgoing outbox message are
    handled inside the transaction controlled by the runtime caller.
    """

    PRODUCER = "globalroamer.chunk-worker"

    def __init__(
        self,
        *,
        chunk_trace: ChunkTrace,
        operational_event_store: OperationalEventStore,
        trace_chunk_store: TraceChunkStore,
        outbox_repository: OutboxRepository,
    ) -> None:
        if not isinstance(
            chunk_trace,
            ChunkTrace,
        ):
            raise TypeError(
                "chunk_trace must be a ChunkTrace"
            )

        if not isinstance(
            operational_event_store,
            OperationalEventStore,
        ):
            raise TypeError(
                "operational_event_store must be an "
                "OperationalEventStore"
            )

        if not isinstance(
            trace_chunk_store,
            TraceChunkStore,
        ):
            raise TypeError(
                "trace_chunk_store must be a TraceChunkStore"
            )

        self._chunk_trace = chunk_trace
        self._operational_event_store = (
            operational_event_store
        )
        self._trace_chunk_store = trace_chunk_store
        self._outbox_repository = outbox_repository

    async def handle(
        self,
        event: EventEnvelope,
    ) -> EventEnvelope:
        """
        Process one TRACE_NORMALIZED event.

        Returns:
            The TRACE_CHUNKED event stored in the transactional outbox.

        Raises:
            TypeError: When the incoming object has an invalid type.
            ValueError: When the event type or payload is invalid.
            Exception: Propagates domain, application, or infrastructure
                failures so the runtime can roll back and retry.
        """
        self._validate_event_type(event)

        command = self._to_command(event)

        logger.info(
            "Chunk worker started",
            extra={
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "correlation_id": event.correlation_id,
                "tenant_id": command.tenant_id,
                "trace_id": command.trace_id,
                "testcase_id": command.testcase_id,
                "stage": "worker.chunk",
            },
        )

        try:
            operational_events = (
                await self._operational_event_store.list_by_trace(
                    tenant_id=command.tenant_id,
                    trace_id=command.trace_id,
                )
            )

            result = self._chunk_trace.execute(
                command=command,
                operational_events=operational_events,
            )

            deleted_chunk_count = (
                await self._trace_chunk_store.delete_by_trace(
                    tenant_id=command.tenant_id,
                    trace_id=command.trace_id,
                )
            )

            await self._trace_chunk_store.save_many(
                result.chunks
            )

            outgoing_event = self._to_chunked_event(
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
                "Chunk worker failed",
                extra={
                    "event_id": str(event.event_id),
                    "event_type": event.event_type,
                    "correlation_id": event.correlation_id,
                    "tenant_id": command.tenant_id,
                    "trace_id": command.trace_id,
                    "testcase_id": command.testcase_id,
                    "stage": "worker.chunk",
                    "error_type": type(exc).__name__,
                },
            )
            raise

        logger.info(
            "Chunk worker completed",
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
                "testcase_id": result.testcase_id,
                "source_event_count": (
                    result.source_event_count
                ),
                "chunk_count": result.chunk_count,
                "deleted_chunk_count": (
                    deleted_chunk_count
                ),
                "stage": "worker.chunk",
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

        if event.event_type != TRACE_NORMALIZED:
            raise ValueError(
                "ChunkWorker supports only "
                f"{TRACE_NORMALIZED!r} events; "
                f"received {event.event_type!r}"
            )

    @classmethod
    def _to_command(
        cls,
        event: EventEnvelope,
    ) -> ChunkTraceCommand:
        """Convert the incoming event into a chunking command."""
        trace_id = cls._required_string(
            event.payload,
            "trace_id",
        )

        testcase_id = cls._optional_string(
            event.payload,
            "testcase_id",
        )

        return ChunkTraceCommand(
            tenant_id=event.tenant_id,
            trace_id=trace_id,
            testcase_id=testcase_id,
        )

    @classmethod
    def _to_chunked_event(
        cls,
        *,
        source_event: EventEnvelope,
        result: ChunkTraceResult,
    ) -> EventEnvelope:
        """
        Create the TRACE_CHUNKED event produced by this worker.

        TraceChunk text and event data are intentionally not embedded in the
        integration event. The payload contains identity, counts, chunk IDs,
        and content hashes. Full chunks remain authoritative in PostgreSQL.
        """
        payload: dict[str, Any] = {
            "trace_id": result.trace_id,
            "testcase_id": result.testcase_id,
            "source_event_count": (
                result.source_event_count
            ),
            "chunk_count": result.chunk_count,
            "chunk_ids": [
                str(chunk.id)
                for chunk in result.chunks
            ],
            "content_hashes": [
                chunk.content_hash
                for chunk in result.chunks
            ],
        }

        return EventEnvelope(
            event_id=uuid4(),
            event_type=TRACE_CHUNKED,
            event_version=1,
            correlation_id=(
                source_event.correlation_id
            ),
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
    def _optional_string(
        payload: dict[str, Any],
        field_name: str,
    ) -> str | None:
        """Read and validate one optional string payload field."""
        value = payload.get(field_name)

        if value is None:
            return None

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise ValueError(
                f"Event payload field {field_name!r} "
                "must be a non-empty string or null"
            )

        return value.strip()
