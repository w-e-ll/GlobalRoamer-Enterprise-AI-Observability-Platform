"""Worker responsible for processing received trace artifacts.

The worker is intentionally independent of a specific message broker. It
accepts an EventEnvelope, invokes the ProcessTrace application use case,
creates a TRACE_PARSED event, and stores that event in the transactional
outbox.

Broker-specific acknowledgement, retry, dead-letter, polling, and transaction
commit behavior belongs in the infrastructure runtime layer.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from globalroamer_platform.application.ports.outbox_repository import (
    OutboxRepository,
)
from globalroamer_platform.application.traces.process_trace import (
    ProcessTrace,
    ProcessTraceCommand,
    ProcessTraceResult,
)
from globalroamer_platform.domain.entities.outbox_message import (
    OutboxMessage,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_ARTIFACT_RECEIVED,
    TRACE_PARSED,
)


logger = logging.getLogger(__name__)


class ParserWorker:
    """Process trace-artifact events and persist outgoing events to the outbox."""

    PRODUCER = "globalroamer.parser-worker"

    def __init__(
        self,
        *,
        process_trace: ProcessTrace,
        outbox_repository: OutboxRepository,
    ) -> None:
        self._process_trace = process_trace
        self._outbox_repository = outbox_repository

    async def handle(
        self,
        event: EventEnvelope,
    ) -> EventEnvelope:
        """Process one trace-artifact event.

        The parsed trace and the outgoing outbox message must be committed by
        the same transaction boundary outside this class.

        Args:
            event: Incoming trace-artifact event.

        Returns:
            The TRACE_PARSED event stored in the transactional outbox.

        Raises:
            ValueError: If the event type or payload is invalid.
            Exception: Propagates application or infrastructure failures so the
                runtime can roll back the transaction and apply retry policy.
        """
        self._validate_event_type(event)

        command = self._to_command(event)

        logger.info(
            "Parser worker started",
            extra={
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "correlation_id": event.correlation_id,
                "tenant_id": event.tenant_id,
                "trace_id": command.trace_id,
                "testcase_id": command.testcase_id,
                "source_path": str(command.source_path),
                "stage": "worker.parser",
            },
        )

        try:
            result = await self._process_trace.execute(
                command
            )

            outgoing_event = self._to_parsed_event(
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
                "Parser worker failed",
                extra={
                    "event_id": str(event.event_id),
                    "event_type": event.event_type,
                    "correlation_id": event.correlation_id,
                    "tenant_id": event.tenant_id,
                    "trace_id": command.trace_id,
                    "testcase_id": command.testcase_id,
                    "source_path": str(command.source_path),
                    "stage": "worker.parser",
                    "error_type": type(exc).__name__,
                },
            )
            raise

        logger.info(
            "Parser worker completed",
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
                "parsed_trace_id": str(
                    result.parsed_trace_id
                ),
                "row_count": result.row_count,
                "warning_count": result.warning_count,
                "error_count": result.error_count,
                "is_valid": result.is_valid,
                "is_complete": result.is_complete,
                "stage": "worker.parser",
            },
        )

        return outgoing_event

    @staticmethod
    def _validate_event_type(
        event: EventEnvelope,
    ) -> None:
        """Ensure the worker received a supported event type."""
        if event.event_type != TRACE_ARTIFACT_RECEIVED:
            raise ValueError(
                "ParserWorker supports only "
                f"{TRACE_ARTIFACT_RECEIVED!r} events; "
                f"received {event.event_type!r}"
            )

    @staticmethod
    def _to_command(
        event: EventEnvelope,
    ) -> ProcessTraceCommand:
        """Convert the incoming event into a ProcessTrace command."""
        source_path = ParserWorker._required_string(
            event.payload,
            "source_path",
        )

        trace_id = ParserWorker._required_string(
            event.payload,
            "trace_id",
        )

        testcase_id = event.payload.get(
            "testcase_id"
        )

        if testcase_id is not None:
            if (
                not isinstance(testcase_id, str)
                or not testcase_id.strip()
            ):
                raise ValueError(
                    "Event payload field 'testcase_id' "
                    "must be a non-empty string or null"
                )

            testcase_id = testcase_id.strip()

        return ProcessTraceCommand(
            source_path=Path(source_path),
            tenant_id=event.tenant_id,
            trace_id=trace_id,
            testcase_id=testcase_id,
        )

    @classmethod
    def _to_parsed_event(
        cls,
        *,
        source_event: EventEnvelope,
        result: ProcessTraceResult,
    ) -> EventEnvelope:
        """Create the TRACE_PARSED event produced by the worker."""
        payload: dict[str, Any] = {
            "parsed_trace_id": str(
                result.parsed_trace_id
            ),
            "trace_id": result.trace_id,
            "testcase_id": result.testcase_id,
            "row_count": result.row_count,
            "evidence_count": result.evidence_count,
            "signal_count": result.signal_count,
            "extracted_value_count": (
                result.extracted_value_count
            ),
            "mapped_value_count": (
                result.mapped_value_count
            ),
            "warning_count": result.warning_count,
            "error_count": result.error_count,
            "is_valid": result.is_valid,
            "is_complete": result.is_complete,
        }

        return EventEnvelope(
            event_id=uuid4(),
            event_type=TRACE_PARSED,
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
