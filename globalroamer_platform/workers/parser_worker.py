"""Worker responsible for processing received trace artifacts.

The worker is independent of a specific message broker. It accepts a
TRACE_ARTIFACT_RECEIVED EventEnvelope, invokes the ProcessArtifact
application use case, creates a TRACE_PARSED event, and stores that event
in the transactional outbox.

Broker acknowledgement, retry, dead-letter handling, polling, transaction
commit, and transaction rollback belong to the infrastructure runtime.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from globalroamer_platform.application.ports.outbox_repository import (
    OutboxRepository,
)
from globalroamer_platform.application.traces.process_artifact import (
    ProcessArtifact,
    ProcessArtifactCommand,
    ProcessArtifactResult,
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
    """
    Process source-artifact events and persist parsed events.

    Artifact lifecycle updates, parsed-trace persistence, and the outgoing
    outbox message share the transaction owned by the outer runtime.
    """

    PRODUCER = "globalroamer.parser-worker"

    def __init__(
        self,
        *,
        process_artifact: ProcessArtifact,
        outbox_repository: OutboxRepository,
    ) -> None:
        self._process_artifact = process_artifact
        self._outbox_repository = (
            outbox_repository
        )

    async def handle(
        self,
        event: EventEnvelope,
    ) -> EventEnvelope:
        """
        Process one TRACE_ARTIFACT_RECEIVED event.

        Args:
            event:
                Incoming source-artifact event.

        Returns:
            TRACE_PARSED event added to the transactional outbox.

        Raises:
            ValueError:
                If the event type or payload is invalid.

            Exception:
                Application and infrastructure failures are propagated so
                the runtime can roll back and apply its retry policy.
        """

        self._validate_event_type(event)

        command = self._to_command(event)

        logger.info(
            "Parser worker started",
            extra={
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "artifact_id": str(
                    command.artifact_id
                ),
                "correlation_id": (
                    event.correlation_id
                ),
                "tenant_id": command.tenant_id,
                "stage": "worker.parser",
            },
        )

        try:
            result = (
                await self._process_artifact.execute(
                    command
                )
            )

            outgoing_event = (
                self._to_parsed_event(
                    source_event=event,
                    result=result,
                )
            )

            outbox_message = OutboxMessage.create(
                event=outgoing_event,
            )

            await self._outbox_repository.add(
                outbox_message,
            )

        except Exception as exc:
            logger.exception(
                "Parser worker failed",
                extra={
                    "event_id": str(
                        event.event_id
                    ),
                    "event_type": (
                        event.event_type
                    ),
                    "artifact_id": str(
                        command.artifact_id
                    ),
                    "correlation_id": (
                        event.correlation_id
                    ),
                    "tenant_id": (
                        command.tenant_id
                    ),
                    "stage": "worker.parser",
                    "error_type": (
                        type(exc).__name__
                    ),
                },
            )
            raise

        trace_result = result.trace_result

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
                "artifact_id": str(
                    result.artifact_id
                ),
                "artifact_status": (
                    result.artifact_status.value
                ),
                "correlation_id": (
                    event.correlation_id
                ),
                "tenant_id": (
                    trace_result.tenant_id
                ),
                "trace_id": (
                    trace_result.trace_id
                ),
                "parsed_trace_id": str(
                    trace_result.parsed_trace_id
                ),
                "row_count": (
                    trace_result.row_count
                ),
                "warning_count": (
                    trace_result.warning_count
                ),
                "error_count": (
                    trace_result.error_count
                ),
                "is_valid": (
                    trace_result.is_valid
                ),
                "is_complete": (
                    trace_result.is_complete
                ),
                "stage": "worker.parser",
            },
        )

        return outgoing_event

    @staticmethod
    def _validate_event_type(
        event: EventEnvelope,
    ) -> None:
        """Ensure that the event type is supported."""

        if (
            event.event_type
            != TRACE_ARTIFACT_RECEIVED
        ):
            raise ValueError(
                "ParserWorker supports only "
                f"{TRACE_ARTIFACT_RECEIVED!r} "
                "events; received "
                f"{event.event_type!r}"
            )

    @staticmethod
    def _to_command(
        event: EventEnvelope,
    ) -> ProcessArtifactCommand:
        """
        Convert the incoming event into a ProcessArtifact command.

        The artifact identifier is now the only location-independent
        reference required by the parser worker.
        """

        artifact_id_value = (
            ParserWorker._required_string(
                event.payload,
                "artifact_id",
            )
        )

        try:
            artifact_id = UUID(
                artifact_id_value
            )
        except ValueError as exc:
            raise ValueError(
                "Event payload field "
                "'artifact_id' must be a valid UUID"
            ) from exc

        return ProcessArtifactCommand(
            artifact_id=artifact_id,
            tenant_id=event.tenant_id,
        )

    @classmethod
    def _to_parsed_event(
        cls,
        *,
        source_event: EventEnvelope,
        result: ProcessArtifactResult,
    ) -> EventEnvelope:
        """Create the TRACE_PARSED event produced by the worker."""

        trace_result = result.trace_result

        payload: dict[str, Any] = {
            "artifact_id": str(
                result.artifact_id
            ),
            "parsed_trace_id": str(
                trace_result.parsed_trace_id
            ),
            "trace_id": trace_result.trace_id,
            "testcase_id": (
                trace_result.testcase_id
            ),
            "row_count": trace_result.row_count,
            "evidence_count": (
                trace_result.evidence_count
            ),
            "signal_count": (
                trace_result.signal_count
            ),
            "extracted_value_count": (
                trace_result.extracted_value_count
            ),
            "mapped_value_count": (
                trace_result.mapped_value_count
            ),
            "warning_count": (
                trace_result.warning_count
            ),
            "error_count": (
                trace_result.error_count
            ),
            "is_valid": (
                trace_result.is_valid
            ),
            "is_complete": (
                trace_result.is_complete
            ),
        }

        return EventEnvelope(
            event_id=uuid4(),
            event_type=TRACE_PARSED,
            event_version=1,
            correlation_id=(
                source_event.correlation_id
            ),
            causation_id=(
                source_event.event_id
            ),
            tenant_id=(
                trace_result.tenant_id
            ),
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
        """Read and validate one required payload string."""

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
