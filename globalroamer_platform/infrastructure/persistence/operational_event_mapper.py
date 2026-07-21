from __future__ import annotations

from globalroamer_platform.domain.models.operational_event import (
    OperationalEvent,
    OperationalEventDirection,
    OperationalEventFamily,
    OperationalEventResult,
    OperationalEventSeverity,
)
from globalroamer_platform.infrastructure.models.operational_event import (
    OperationalEventModel,
)


class OperationalEventMapper:
    """
    Map between immutable OperationalEvent domain objects and SQLAlchemy
    persistence models.

    The mapper contains no database access and performs no transaction
    management.
    """

    @staticmethod
    def to_model(
        event: OperationalEvent,
    ) -> OperationalEventModel:
        """Create a persistence model from one domain event."""

        if not isinstance(event, OperationalEvent):
            raise TypeError(
                "event must be an OperationalEvent"
            )

        return OperationalEventModel(
            id=event.id,
            tenant_id=event.tenant_id,
            trace_id=event.trace_id,
            testcase_id=event.testcase_id,
            sequence_number=event.sequence_number,
            event_name=event.event_name,
            event_family=event.event_family.value,
            severity=event.severity.value,
            raw_message=event.raw_message,
            normalized_message=event.normalized_message,
            source_line_number=event.source_line_number,
            timestamp=event.timestamp,
            protocol_layer=event.protocol_layer,
            direction=event.direction.value,
            result=event.result.value,
            workflow_stage=event.workflow_stage,
            network_domain=event.network_domain,
            operator=event.operator,
            country=event.country,
            cause=event.cause,
            retry_recommended=event.retry_recommended,
            recommendation=event.recommendation,
            tags=list(event.tags),
            evidence_lines=list(
                event.evidence_lines
            ),
            extracted_values=dict(
                event.extracted_values
            ),
            event_metadata=dict(event.metadata),
        )

    @staticmethod
    def to_domain(
        model: OperationalEventModel,
    ) -> OperationalEvent:
        """Reconstruct one domain event from a persistence model."""

        if not isinstance(
            model,
            OperationalEventModel,
        ):
            raise TypeError(
                "model must be an OperationalEventModel"
            )

        return OperationalEvent(
            id=model.id,
            tenant_id=model.tenant_id,
            trace_id=model.trace_id,
            testcase_id=model.testcase_id,
            sequence_number=model.sequence_number,
            event_name=model.event_name,
            event_family=OperationalEventFamily(
                model.event_family
            ),
            severity=OperationalEventSeverity(
                model.severity
            ),
            raw_message=model.raw_message,
            normalized_message=(
                model.normalized_message
            ),
            source_line_number=(
                model.source_line_number
            ),
            timestamp=model.timestamp,
            protocol_layer=model.protocol_layer,
            direction=OperationalEventDirection(
                model.direction
            ),
            result=OperationalEventResult(
                model.result
            ),
            workflow_stage=model.workflow_stage,
            network_domain=model.network_domain,
            operator=model.operator,
            country=model.country,
            cause=model.cause,
            retry_recommended=(
                model.retry_recommended
            ),
            recommendation=model.recommendation,
            tags=tuple(model.tags or ()),
            evidence_lines=tuple(
                model.evidence_lines or ()
            ),
            extracted_values=dict(
                model.extracted_values or {}
            ),
            metadata=dict(
                model.event_metadata or {}
            ),
        )

    @classmethod
    def to_models(
        cls,
        events: tuple[
            OperationalEvent,
            ...,
        ],
    ) -> tuple[
        OperationalEventModel,
        ...,
    ]:
        """Map multiple domain events to persistence models."""

        if not isinstance(events, tuple):
            raise TypeError(
                "events must be a tuple"
            )

        return tuple(
            cls.to_model(event)
            for event in events
        )

    @classmethod
    def to_domains(
        cls,
        models: tuple[
            OperationalEventModel,
            ...,
        ],
    ) -> tuple[
        OperationalEvent,
        ...,
    ]:
        """Map multiple persistence models to domain events."""

        if not isinstance(models, tuple):
            raise TypeError(
                "models must be a tuple"
            )

        return tuple(
            cls.to_domain(model)
            for model in models
        )
