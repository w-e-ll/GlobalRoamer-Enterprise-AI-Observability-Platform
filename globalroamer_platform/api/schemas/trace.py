from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from globalroamer_platform.domain.entities.trace import Trace


class CreateTraceRequest(BaseModel):
    """Request payload for creating a trace."""

    tenant_id: str = Field(..., min_length=1, max_length=100)
    trace_id: str = Field(..., min_length=1, max_length=128)
    testcase_id: str = Field(..., min_length=1, max_length=128)


class TraceResponse(BaseModel):
    """API representation of a trace."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    trace_id: str
    testcase_id: str

    status: str
    current_stage: str

    version: int

    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, trace: Trace) -> "TraceResponse":
        return cls(
            id=trace.id,
            tenant_id=trace.tenant_id,
            trace_id=trace.trace_id,
            testcase_id=trace.testcase_id,
            status=trace.status.value,
            current_stage=trace.current_stage,
            version=trace.version,
            created_at=trace.created_at,
            updated_at=trace.updated_at,
        )


class TraceListResponse(BaseModel):
    """Paginated trace collection."""

    items: list[TraceResponse]
    total: int
