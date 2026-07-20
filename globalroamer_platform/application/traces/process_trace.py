from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from globalroamer_platform.application.traces.parse_trace import (
    ParseTrace,
    ParseTraceCommand,
)
from globalroamer_platform.domain.models.parsed_trace import ParsedTrace
from globalroamer_platform.domain.services.trace_loader import TraceLoader


class ParsedTraceStorePort(Protocol):
    """Application-facing parsed-trace persistence contract."""

    async def save(
        self,
        parsed_trace: ParsedTrace,
    ) -> object:
        """Persist the parsed trace and return its stored representation."""


@dataclass(frozen=True, slots=True)
class ProcessTraceCommand:
    """Input for loading, parsing, and persisting one trace."""

    source_path: Path
    tenant_id: str
    trace_id: str
    testcase_id: str | None = None

    def __post_init__(self) -> None:
        tenant_id = self.tenant_id.strip()
        trace_id = self.trace_id.strip()

        testcase_id = (
            self.testcase_id.strip()
            if self.testcase_id is not None
            else None
        )

        if not tenant_id:
            raise ValueError("tenant_id must not be empty")

        if not trace_id:
            raise ValueError("trace_id must not be empty")

        if testcase_id == "":
            testcase_id = None

        object.__setattr__(
            self,
            "source_path",
            Path(self.source_path),
        )
        object.__setattr__(
            self,
            "tenant_id",
            tenant_id,
        )
        object.__setattr__(
            self,
            "trace_id",
            trace_id,
        )
        object.__setattr__(
            self,
            "testcase_id",
            testcase_id,
        )


@dataclass(frozen=True, slots=True)
class ProcessTraceResult:
    """Summary returned after successful trace persistence."""

    parsed_trace_id: UUID
    tenant_id: str
    trace_id: str
    testcase_id: str | None

    row_count: int
    evidence_count: int
    signal_count: int
    extracted_value_count: int
    mapped_value_count: int

    warning_count: int
    error_count: int

    is_valid: bool
    is_complete: bool


class ProcessTrace:
    """
    Load, parse, and persist one trace.

    This use case does not commit the database transaction. Transaction
    ownership belongs to the worker runtime or application boundary.
    """

    def __init__(
        self,
        *,
        trace_loader: TraceLoader,
        parse_trace: ParseTrace,
        parsed_trace_store: ParsedTraceStorePort,
    ) -> None:
        self._trace_loader = trace_loader
        self._parse_trace = parse_trace
        self._parsed_trace_store = parsed_trace_store

    async def execute(
        self,
        command: ProcessTraceCommand,
    ) -> ProcessTraceResult:
        source_artifact = self._trace_loader.load(
            command.source_path,
            tenant_id=command.tenant_id,
            trace_id=command.trace_id,
            testcase_id=command.testcase_id,
        )

        parse_result = self._parse_trace.execute(
            ParseTraceCommand(
                source=source_artifact,
                metadata={
                    "tenant_id": command.tenant_id,
                    "trace_id": command.trace_id,
                    "testcase_id": command.testcase_id,
                    "source_artifact_id": str(source_artifact.id),
                },
            )
        )

        stored_model = await self._parsed_trace_store.save(
            parse_result.parsed_trace
        )

        return ProcessTraceResult(
            parsed_trace_id=stored_model.id,
            tenant_id=stored_model.tenant_id,
            trace_id=stored_model.trace_id,
            testcase_id=stored_model.testcase_id,
            row_count=stored_model.row_count,
            evidence_count=stored_model.evidence_count,
            signal_count=stored_model.signal_count,
            extracted_value_count=(
                stored_model.extracted_value_count
            ),
            mapped_value_count=(
                stored_model.mapped_value_count
            ),
            warning_count=stored_model.warning_count,
            error_count=stored_model.error_count,
            is_valid=stored_model.is_valid,
            is_complete=stored_model.is_complete,
        )
