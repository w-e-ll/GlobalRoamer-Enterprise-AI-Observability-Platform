"""Worker responsible for normalizing persisted parsed traces.

The worker accepts a TRACE_PARSED event, reloads the authoritative
ParsedTrace aggregate from PostgreSQL, invokes the NormalizeTrace
application use case, creates a TRACE_NORMALIZED event, and stores that
event in the transactional outbox.

The worker does not commit or roll back the database transaction.
Transaction ownership belongs to the infrastructure runtime.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from globalroamer_platform.application.ports.outbox_repository import (
    OutboxRepository,
)
from globalroamer_platform.application.traces.normalize_trace import (
    NormalizeTrace,
    NormalizeTraceCommand,
    NormalizeTraceResult,
)
from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_NORMALIZED,
    TRACE_PARSED,
)
from globalroamer_platform.infrastructure.persistence.parsed_trace_store import (
    ParsedTraceStore,
)
from globalroamer_platform.infrastructure.persistence.operational_event_store import (
    OperationalEventStore,
)


logger = logging.getLogger(__name__)


class NormalizerWorker:
    """
    Normalize persisted parsed traces and enqueue outgoing events.

    The ParsedTrace snapshot and outgoing outbox message are read and written
    inside the transaction controlled by the runtime caller.
    """

    PRODUCER = "globalroamer.normalizer-worker"

    def __init__(
        self,
        *,
        normalize_trace: NormalizeTrace,
        parsed_trace_store: ParsedTraceStore,
        operational_event_store: OperationalEventStore,
        outbox_repository: OutboxRepository,
    ) -> None:
        if not isinstance(
            normalize_trace,
            NormalizeTrace,
        ):
            raise TypeError(
                "normalize_trace must be a NormalizeTrace"
            )

        if not isinstance(
            parsed_trace_store,
            ParsedTraceStore,
        ):
            raise TypeError(
                "parsed_trace_store must be a ParsedTraceStore"
            )

        if not isinstance(
                operational_event_store,
                OperationalEventStore,
        ):
            raise TypeError(
                "operational_event_store must be an OperationalEventStore"
            )

        self._normalize_trace = normalize_trace
        self._parsed_trace_store = parsed_trace_store
        self._operational_event_store = operational_event_store
        self._outbox_repository = outbox_repository

    async def handle(
        self,
        event: EventEnvelope,
    ) -> EventEnvelope:
        """
        Process one TRACE_PARSED event.

        Returns:
            The TRACE_NORMALIZED event stored in the transactional outbox.

        Raises:
            ValueError: When the incoming event or payload is invalid.
            LookupError: When the persisted ParsedTrace cannot be found.
            Exception: Propagates domain, application, or infrastructure
                failures so the runtime can roll back and retry.
        """
        self._validate_event_type(event)

        command = self._to_command(event)

        logger.info(
            "Normalizer worker started",
            extra={
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "correlation_id": event.correlation_id,
                "tenant_id": command.tenant_id,
                "trace_id": command.trace_id,
                "testcase_id": command.testcase_id,
                "parsed_trace_id": str(
                    command.parsed_trace_id
                ),
                "stage": "worker.normalizer",
            },
        )

        try:
            parsed_trace = (
                await self._parsed_trace_store.get_domain(
                    tenant_id=command.tenant_id,
                    trace_id=command.trace_id,
                )
            )

            if parsed_trace is None:
                raise LookupError(
                    "Persisted ParsedTrace was not found: "
                    f"tenant_id={command.tenant_id!r}, "
                    f"trace_id={command.trace_id!r}"
                )

            result = self._normalize_trace.execute(
                command=command,
                parsed_trace=parsed_trace,
            )

            await self._operational_event_store.save_many(
                result.operational_events
            )

            outgoing_event = self._to_normalized_event(
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
                "Normalizer worker failed",
                extra={
                    "event_id": str(event.event_id),
                    "event_type": event.event_type,
                    "correlation_id": event.correlation_id,
                    "tenant_id": command.tenant_id,
                    "trace_id": command.trace_id,
                    "testcase_id": command.testcase_id,
                    "parsed_trace_id": str(
                        command.parsed_trace_id
                    ),
                    "stage": "worker.normalizer",
                    "error_type": type(exc).__name__,
                },
            )
            raise

        logger.info(
            "Normalizer worker completed",
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
                "parsed_trace_id": str(
                    result.parsed_trace_id
                ),
                "source_evidence_count": (
                    result.source_evidence_count
                ),
                "operational_event_count": (
                    result.operational_event_count
                ),
                "failure_event_count": (
                    result.failure_event_count
                ),
                "high_severity_event_count": (
                    result.high_severity_event_count
                ),
                "retry_recommended_count": (
                    result.retry_recommended_count
                ),
                "stage": "worker.normalizer",
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

        if event.event_type != TRACE_PARSED:
            raise ValueError(
                "NormalizerWorker supports only "
                f"{TRACE_PARSED!r} events; "
                f"received {event.event_type!r}"
            )

    @classmethod
    def _to_command(
        cls,
        event: EventEnvelope,
    ) -> NormalizeTraceCommand:
        """Convert the incoming event into a normalization command."""
        parsed_trace_id = cls._required_uuid(
            event.payload,
            "parsed_trace_id",
        )

        trace_id = cls._required_string(
            event.payload,
            "trace_id",
        )

        testcase_id = cls._optional_string(
            event.payload,
            "testcase_id",
        )

        return NormalizeTraceCommand(
            parsed_trace_id=parsed_trace_id,
            tenant_id=event.tenant_id,
            trace_id=trace_id,
            testcase_id=testcase_id,
        )

    @classmethod
    def _to_normalized_event(
        cls,
        *,
        source_event: EventEnvelope,
        result: NormalizeTraceResult,
    ) -> EventEnvelope:
        """
        Create the TRACE_NORMALIZED event produced by this worker.

        OperationalEvent objects are intentionally not embedded in the
        integration event. The payload contains identity and summary data.
        Operational events will be persisted separately.
        """
        payload: dict[str, Any] = {
            "parsed_trace_id": str(
                result.parsed_trace_id
            ),
            "trace_id": result.trace_id,
            "testcase_id": result.testcase_id,
            "source_evidence_count": (
                result.source_evidence_count
            ),
            "operational_event_count": (
                result.operational_event_count
            ),
            "failure_event_count": (
                result.failure_event_count
            ),
            "high_severity_event_count": (
                result.high_severity_event_count
            ),
            "retry_recommended_count": (
                result.retry_recommended_count
            ),
        }

        return EventEnvelope(
            event_id=uuid4(),
            event_type=TRACE_NORMALIZED,
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

    @staticmethod
    def _required_uuid(
        payload: dict[str, Any],
        field_name: str,
    ) -> UUID:
        """Read and validate one required UUID payload field."""
        value = payload.get(field_name)

        if isinstance(value, UUID):
            return value

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise ValueError(
                "Event payload must contain a "
                f"non-empty {field_name!r} UUID string"
            )

        try:
            return UUID(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"Event payload field {field_name!r} "
                "must contain a valid UUID"
            ) from exc
