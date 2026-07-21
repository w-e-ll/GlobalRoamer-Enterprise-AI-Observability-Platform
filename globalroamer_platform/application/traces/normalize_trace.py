from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from globalroamer_platform.domain.models.operational_event import (
    OperationalEvent,
)
from globalroamer_platform.domain.models.parsed_trace import (
    ParsedTrace,
)
from globalroamer_platform.domain.services.trace_normalizer import (
    TraceNormalizer,
)


@dataclass(frozen=True, slots=True)
class NormalizeTraceCommand:
    """Identity and context required to normalize a parsed trace."""

    parsed_trace_id: UUID
    tenant_id: str
    trace_id: str
    testcase_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.parsed_trace_id,
            UUID,
        ):
            raise TypeError(
                "parsed_trace_id must be a UUID"
            )

        if not isinstance(
            self.tenant_id,
            str,
        ):
            raise TypeError(
                "tenant_id must be a string"
            )

        if not isinstance(
            self.trace_id,
            str,
        ):
            raise TypeError(
                "trace_id must be a string"
            )

        if (
            self.testcase_id is not None
            and not isinstance(
                self.testcase_id,
                str,
            )
        ):
            raise TypeError(
                "testcase_id must be a string or None"
            )

        normalized_tenant_id = (
            self.tenant_id.strip()
        )
        normalized_trace_id = (
            self.trace_id.strip()
        )
        normalized_testcase_id = (
            self.testcase_id.strip()
            if self.testcase_id is not None
            else None
        )

        if not normalized_tenant_id:
            raise ValueError(
                "tenant_id must not be empty"
            )

        if not normalized_trace_id:
            raise ValueError(
                "trace_id must not be empty"
            )

        object.__setattr__(
            self,
            "tenant_id",
            normalized_tenant_id,
        )
        object.__setattr__(
            self,
            "trace_id",
            normalized_trace_id,
        )
        object.__setattr__(
            self,
            "testcase_id",
            normalized_testcase_id or None,
        )


@dataclass(frozen=True, slots=True)
class NormalizeTraceResult:
    """Summary produced after successful trace normalization."""

    parsed_trace_id: UUID

    tenant_id: str
    trace_id: str
    testcase_id: str | None

    source_evidence_count: int
    operational_event_count: int

    failure_event_count: int
    high_severity_event_count: int
    retry_recommended_count: int

    operational_events: tuple[
        OperationalEvent,
        ...,
    ]


class NormalizeTrace:
    """
    Normalize an already reconstructed ParsedTrace aggregate.

    The use case applies domain normalization and returns operational
    events. It does not:

    - load persistence models;
    - commit database transactions;
    - publish integration events;
    - write transactional outbox messages;
    - acknowledge broker messages.

    Persistence and transaction ownership belong to the worker and
    infrastructure layers.
    """

    def __init__(
        self,
        *,
        trace_normalizer: TraceNormalizer,
    ) -> None:
        if not isinstance(
            trace_normalizer,
            TraceNormalizer,
        ):
            raise TypeError(
                "trace_normalizer must be a TraceNormalizer"
            )

        self._trace_normalizer = (
            trace_normalizer
        )

    def execute(
        self,
        *,
        command: NormalizeTraceCommand,
        parsed_trace: ParsedTrace,
    ) -> NormalizeTraceResult:
        """Normalize one parsed trace aggregate."""

        if not isinstance(
            command,
            NormalizeTraceCommand,
        ):
            raise TypeError(
                "command must be a NormalizeTraceCommand"
            )

        if not isinstance(
            parsed_trace,
            ParsedTrace,
        ):
            raise TypeError(
                "parsed_trace must be a ParsedTrace"
            )

        self._validate_identity(
            parsed_trace=parsed_trace,
            command=command,
        )

        operational_events = (
            self._trace_normalizer.normalize(
                parsed_trace
            )
        )

        return NormalizeTraceResult(
            parsed_trace_id=command.parsed_trace_id,
            tenant_id=command.tenant_id,
            trace_id=command.trace_id,
            testcase_id=command.testcase_id,
            source_evidence_count=(
                parsed_trace.evidence_count
            ),
            operational_event_count=len(
                operational_events
            ),
            failure_event_count=sum(
                1
                for event in operational_events
                if event.is_failure
            ),
            high_severity_event_count=sum(
                1
                for event in operational_events
                if event.is_high_severity
            ),
            retry_recommended_count=sum(
                1
                for event in operational_events
                if event.retry_recommended
            ),
            operational_events=operational_events,
        )

    @staticmethod
    def _validate_identity(
        *,
        parsed_trace: ParsedTrace,
        command: NormalizeTraceCommand,
    ) -> None:
        """
        Ensure the aggregate belongs to the identity carried by the event.

        This protects against cross-tenant processing and malformed event
        payloads.
        """

        stored_tenant_id = (
            parsed_trace.metadata.get(
                "tenant_id"
            )
        )
        stored_trace_id = (
            parsed_trace.metadata.get(
                "trace_id"
            )
        )
        stored_testcase_id = (
            parsed_trace.metadata.get(
                "testcase_id"
            )
        )

        if stored_tenant_id != command.tenant_id:
            raise ValueError(
                "ParsedTrace tenant_id does not match "
                "NormalizeTraceCommand: "
                f"{stored_tenant_id!r} != "
                f"{command.tenant_id!r}"
            )

        if stored_trace_id != command.trace_id:
            raise ValueError(
                "ParsedTrace trace_id does not match "
                "NormalizeTraceCommand: "
                f"{stored_trace_id!r} != "
                f"{command.trace_id!r}"
            )

        if (
            command.testcase_id is not None
            and stored_testcase_id
            != command.testcase_id
        ):
            raise ValueError(
                "ParsedTrace testcase_id does not match "
                "NormalizeTraceCommand: "
                f"{stored_testcase_id!r} != "
                f"{command.testcase_id!r}"
            )
