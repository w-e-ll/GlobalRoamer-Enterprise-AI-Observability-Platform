"""API schemas for trace-processing operations.

This module defines the HTTP request and response contracts used to expose
the trace-processing application workflow through FastAPI.

The schemas contain no persistence or infrastructure behavior. They validate
external input and serialize application-layer results.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProcessTraceRequest(BaseModel):
    """Request payload for processing and persisting one trace file."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "source_path": "etc/sample_trace.csv",
                "tenant_id": "smoke-test",
                "trace_id": "process-trace-001",
                "testcase_id": "process-trace-001",
            }
        },
    )

    source_path: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description=(
            "Path to a trace file available inside the API runtime."
        ),
    )
    tenant_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Tenant that owns the trace.",
    )
    trace_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="External identifier of the trace.",
    )
    testcase_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description=(
            "Optional testcase identifier associated with the trace."
        ),
    )

    @field_validator("source_path")
    @classmethod
    def validate_source_path(
        cls,
        value: str,
    ) -> str:
        """Validate and normalize the supplied source path.

        File existence, directory containment, extension validation, and size
        validation remain responsibilities of TraceLoader.

        Args:
            value: Source path supplied by the API consumer.

        Returns:
            Normalized filesystem path string.

        Raises:
            ValueError: If the path contains a null byte.
        """
        if "\x00" in value:
            raise ValueError(
                "source_path must not contain null bytes"
            )

        return str(
            Path(value).expanduser()
        )


class ProcessTraceResponse(BaseModel):
    """Response returned after successful trace processing and persistence."""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        json_schema_extra={
            "example": {
                "parsed_trace_id": (
                    "9d890946-cb38-44f1-818c-c6bb16838833"
                ),
                "tenant_id": "smoke-test",
                "trace_id": "process-trace-001",
                "testcase_id": "process-trace-001",
                "row_count": 3,
                "evidence_count": 3,
                "signal_count": 9,
                "extracted_value_count": 9,
                "mapped_value_count": 6,
                "warning_count": 0,
                "error_count": 0,
                "is_valid": True,
                "is_complete": True,
            }
        },
    )

    parsed_trace_id: UUID = Field(
        ...,
        description=(
            "Identifier of the persisted parsed-trace record."
        ),
    )
    tenant_id: str = Field(
        ...,
        description="Tenant that owns the processed trace.",
    )
    trace_id: str = Field(
        ...,
        description="External trace identifier.",
    )
    testcase_id: str | None = Field(
        default=None,
        description=(
            "Optional testcase identifier associated with the trace."
        ),
    )

    row_count: int = Field(
        ...,
        ge=0,
        description="Number of rows loaded from the trace.",
    )
    evidence_count: int = Field(
        ...,
        ge=0,
        description="Number of evidence records extracted.",
    )
    signal_count: int = Field(
        ...,
        ge=0,
        description="Number of signals extracted.",
    )
    extracted_value_count: int = Field(
        ...,
        ge=0,
        description="Number of values extracted from the trace.",
    )
    mapped_value_count: int = Field(
        ...,
        ge=0,
        description="Number of values mapped successfully.",
    )

    warning_count: int = Field(
        ...,
        ge=0,
        description="Number of processing warnings.",
    )
    error_count: int = Field(
        ...,
        ge=0,
        description="Number of processing errors.",
    )

    is_valid: bool = Field(
        ...,
        description=(
            "Whether the resulting parsed trace passed validation."
        ),
    )
    is_complete: bool = Field(
        ...,
        description=(
            "Whether processing completed with all required data."
        ),
    )
