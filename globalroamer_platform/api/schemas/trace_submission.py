"""HTTP schemas for asynchronous trace submission."""

from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SubmitTraceRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    source_path: str = Field(..., min_length=1, max_length=4096)
    tenant_id: str = Field(..., min_length=1, max_length=100)
    trace_id: str = Field(..., min_length=1, max_length=128)
    testcase_id: str = Field(..., min_length=1, max_length=128)

    @field_validator("source_path")
    @classmethod
    def validate_source_path(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("source_path must not contain null bytes")
        return str(Path(value).expanduser())


class SubmitTraceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_event_id: UUID
    outbox_message_id: UUID
    tenant_id: str
    trace_id: str
    testcase_id: str
    correlation_id: str
    status: str
