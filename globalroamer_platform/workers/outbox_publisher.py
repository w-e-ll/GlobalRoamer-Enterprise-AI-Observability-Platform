"""Broker-agnostic publisher for event envelopes.

This component delegates event delivery to an injected EventPublisher port.

A broker-specific adapter may later implement this port using Kafka,
RabbitMQ, Redis Streams, Azure Service Bus, AWS SNS/SQS, or another
transport.

This class does not persist transactional outbox records yet. It represents
the publishing boundary that can later be connected to a real outbox table
and polling runtime.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from globalroamer_platform.application.ports.event_publisher import (
    EventPublisher,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)


logger = logging.getLogger(__name__)


class OutboxPublisher:
    """Publish event envelopes through an injected transport adapter."""

    def __init__(
        self,
        *,
        event_publisher: EventPublisher,
    ) -> None:
        self._event_publisher = event_publisher

    async def publish(
        self,
        event: EventEnvelope,
    ) -> None:
        """Publish one event envelope.

        Transport exceptions are deliberately propagated so that the worker
        runtime can apply retries or dead-letter handling.
        """
        self._validate_event(event)

        logger.info(
            "Outbox event publishing started",
            extra={
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "event_version": event.event_version,
                "correlation_id": event.correlation_id,
                "causation_id": (
                    str(event.causation_id)
                    if event.causation_id is not None
                    else None
                ),
                "tenant_id": event.tenant_id,
                "producer": event.producer,
                "stage": "worker.outbox_publish",
            },
        )

        try:
            await self._event_publisher.publish(event)
        except Exception as exc:
            logger.exception(
                "Outbox event publishing failed",
                extra={
                    "event_id": str(event.event_id),
                    "event_type": event.event_type,
                    "correlation_id": event.correlation_id,
                    "tenant_id": event.tenant_id,
                    "stage": "worker.outbox_publish",
                    "error_type": type(exc).__name__,
                },
            )
            raise

        logger.info(
            "Outbox event publishing completed",
            extra={
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "correlation_id": event.correlation_id,
                "tenant_id": event.tenant_id,
                "stage": "worker.outbox_publish",
            },
        )

    async def publish_many(
        self,
        events: Sequence[EventEnvelope],
    ) -> None:
        """Publish events sequentially in their supplied order.

        Sequential publication preserves ordering. Processing stops when one
        event fails, and the original exception is propagated.
        """
        for event in events:
            await self.publish(event)

    @staticmethod
    def _validate_event(
        event: EventEnvelope,
    ) -> None:
        """Validate fields required by the publishing boundary."""
        if not event.event_type.strip():
            raise ValueError("event_type must not be empty")

        if event.event_version <= 0:
            raise ValueError(
                "event_version must be greater than zero"
            )

        if not event.correlation_id.strip():
            raise ValueError(
                "correlation_id must not be empty"
            )

        if not event.tenant_id.strip():
            raise ValueError("tenant_id must not be empty")

        if not event.producer.strip():
            raise ValueError("producer must not be empty")
