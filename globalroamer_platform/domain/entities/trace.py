from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from globalroamer_platform.domain.models.processing_status import (
    ProcessingStatus,
)


@dataclass(frozen=True, slots=True)
class Trace:
    """Domain entity representing one trace processing lifecycle."""

    id: UUID
    tenant_id: str
    trace_id: str
    testcase_id: str
    status: ProcessingStatus
    current_stage: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        trace_id: str,
        testcase_id: str,
    ) -> "Trace":
        """Create a new trace in its initial state."""
        normalized_tenant_id = tenant_id.strip()
        normalized_trace_id = trace_id.strip()
        normalized_testcase_id = testcase_id.strip()

        if not normalized_tenant_id:
            raise ValueError("tenant_id must not be empty")

        if not normalized_trace_id:
            raise ValueError("trace_id must not be empty")

        if not normalized_testcase_id:
            raise ValueError("testcase_id must not be empty")

        now = datetime.now(timezone.utc)

        return cls(
            id=uuid4(),
            tenant_id=normalized_tenant_id,
            trace_id=normalized_trace_id,
            testcase_id=normalized_testcase_id,
            status=ProcessingStatus.CREATED,
            current_stage="received",
            version=1,
            created_at=now,
            updated_at=now,
        )

    def start_processing(self, *, stage: str) -> "Trace":
        """Move the trace into active processing."""
        normalized_stage = stage.strip()

        if not normalized_stage:
            raise ValueError("stage must not be empty")

        if self.status == ProcessingStatus.COMPLETED:
            raise ValueError("A completed trace cannot restart processing")

        return self._transition(
            status=ProcessingStatus.PROCESSING,
            current_stage=normalized_stage,
        )

    def complete(self) -> "Trace":
        """Mark processing as successfully completed."""
        if self.status == ProcessingStatus.FAILED:
            raise ValueError("A failed trace cannot be completed")

        return self._transition(
            status=ProcessingStatus.COMPLETED,
            current_stage="completed",
        )

    def fail(self, *, stage: str) -> "Trace":
        """Mark processing as failed at a particular stage."""
        normalized_stage = stage.strip()

        if not normalized_stage:
            raise ValueError("stage must not be empty")

        if self.status == ProcessingStatus.COMPLETED:
            raise ValueError("A completed trace cannot be marked as failed")

        return self._transition(
            status=ProcessingStatus.FAILED,
            current_stage=normalized_stage,
        )

    def _transition(
        self,
        *,
        status: ProcessingStatus,
        current_stage: str,
    ) -> "Trace":
        """Return a new entity instance with an updated lifecycle state."""
        return replace(
            self,
            status=status,
            current_stage=current_stage,
            version=self.version + 1,
            updated_at=datetime.now(timezone.utc),
        )
