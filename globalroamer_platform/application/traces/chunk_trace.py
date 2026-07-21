from __future__ import annotations

from dataclasses import dataclass

from globalroamer_platform.domain.models.operational_event import (
    OperationalEvent,
)
from globalroamer_platform.domain.models.trace_chunk import (
    TraceChunk,
)
from globalroamer_platform.domain.services.trace_chunker import (
    TraceChunker,
)


@dataclass(frozen=True, slots=True)
class ChunkTraceCommand:
    """
    Identifies the trace whose normalized OperationalEvents must be chunked.
    """

    tenant_id: str
    trace_id: str
    testcase_id: str | None = None

    def __post_init__(self) -> None:
        self._validate_required_text(
            value=self.tenant_id,
            field_name="tenant_id",
        )
        self._validate_required_text(
            value=self.trace_id,
            field_name="trace_id",
        )
        self._validate_optional_text(
            value=self.testcase_id,
            field_name="testcase_id",
        )

    @staticmethod
    def _validate_required_text(
        *,
        value: str,
        field_name: str,
    ) -> None:
        if not isinstance(value, str):
            raise TypeError(
                f"{field_name} must be a string"
            )

        if not value.strip():
            raise ValueError(
                f"{field_name} must not be empty"
            )

        if value != value.strip():
            raise ValueError(
                f"{field_name} must be normalized"
            )

    @staticmethod
    def _validate_optional_text(
        *,
        value: str | None,
        field_name: str,
    ) -> None:
        if value is None:
            return

        if not isinstance(value, str):
            raise TypeError(
                f"{field_name} must be a string or None"
            )

        if not value.strip():
            raise ValueError(
                f"{field_name} must not be empty"
            )

        if value != value.strip():
            raise ValueError(
                f"{field_name} must be normalized"
            )


@dataclass(frozen=True, slots=True)
class ChunkTraceResult:
    """
    Result of transforming normalized OperationalEvents into TraceChunks.
    """

    tenant_id: str
    trace_id: str
    testcase_id: str | None
    source_event_count: int
    chunk_count: int
    chunks: tuple[TraceChunk, ...]

    def __post_init__(self) -> None:
        self._validate_required_text(
            value=self.tenant_id,
            field_name="tenant_id",
        )
        self._validate_required_text(
            value=self.trace_id,
            field_name="trace_id",
        )
        self._validate_optional_text(
            value=self.testcase_id,
            field_name="testcase_id",
        )
        self._validate_count(
            value=self.source_event_count,
            field_name="source_event_count",
        )
        self._validate_count(
            value=self.chunk_count,
            field_name="chunk_count",
        )

        if not isinstance(self.chunks, tuple):
            raise TypeError(
                "chunks must be a tuple"
            )

        for chunk in self.chunks:
            if not isinstance(chunk, TraceChunk):
                raise TypeError(
                    "every chunks item must be a TraceChunk"
                )

        if self.chunk_count != len(self.chunks):
            raise ValueError(
                "chunk_count must equal the number of chunks"
            )

        if self.source_event_count == 0 and self.chunks:
            raise ValueError(
                "zero source events cannot produce chunks"
            )

        if self.source_event_count > 0 and not self.chunks:
            raise ValueError(
                "source events must produce at least one chunk"
            )

        for expected_index, chunk in enumerate(
            self.chunks
        ):
            if chunk.tenant_id != self.tenant_id:
                raise ValueError(
                    "all chunks must have the result tenant_id"
                )

            if chunk.trace_id != self.trace_id:
                raise ValueError(
                    "all chunks must have the result trace_id"
                )

            if chunk.testcase_id != self.testcase_id:
                raise ValueError(
                    "all chunks must have the result testcase_id"
                )

            if chunk.chunk_index != expected_index:
                raise ValueError(
                    "chunks must have sequential indexes "
                    "starting from zero"
                )

    @staticmethod
    def _validate_required_text(
        *,
        value: str,
        field_name: str,
    ) -> None:
        if not isinstance(value, str):
            raise TypeError(
                f"{field_name} must be a string"
            )

        if not value.strip():
            raise ValueError(
                f"{field_name} must not be empty"
            )

        if value != value.strip():
            raise ValueError(
                f"{field_name} must be normalized"
            )

    @staticmethod
    def _validate_optional_text(
        *,
        value: str | None,
        field_name: str,
    ) -> None:
        if value is None:
            return

        if not isinstance(value, str):
            raise TypeError(
                f"{field_name} must be a string or None"
            )

        if not value.strip():
            raise ValueError(
                f"{field_name} must not be empty"
            )

        if value != value.strip():
            raise ValueError(
                f"{field_name} must be normalized"
            )

    @staticmethod
    def _validate_count(
        *,
        value: int,
        field_name: str,
    ) -> None:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
        ):
            raise TypeError(
                f"{field_name} must be an integer"
            )

        if value < 0:
            raise ValueError(
                f"{field_name} must be greater than or "
                "equal to zero"
            )


class ChunkTrace:
    """
    Application use case for chunking normalized OperationalEvents.

    This use case coordinates the domain service but performs no persistence,
    transaction handling, logging, event publishing, or infrastructure work.
    """

    def __init__(
        self,
        *,
        trace_chunker: TraceChunker,
    ) -> None:
        if not isinstance(trace_chunker, TraceChunker):
            raise TypeError(
                "trace_chunker must be a TraceChunker"
            )

        self._trace_chunker = trace_chunker

    def execute(
        self,
        *,
        command: ChunkTraceCommand,
        operational_events: tuple[
            OperationalEvent,
            ...,
        ],
    ) -> ChunkTraceResult:
        if not isinstance(command, ChunkTraceCommand):
            raise TypeError(
                "command must be a ChunkTraceCommand"
            )

        self._validate_events_collection(
            operational_events
        )

        self._validate_command_matches_events(
            command=command,
            operational_events=operational_events,
        )

        chunks = self._trace_chunker.chunk(
            operational_events
        )

        return ChunkTraceResult(
            tenant_id=command.tenant_id,
            trace_id=command.trace_id,
            testcase_id=command.testcase_id,
            source_event_count=len(
                operational_events
            ),
            chunk_count=len(chunks),
            chunks=chunks,
        )

    @staticmethod
    def _validate_events_collection(
        operational_events: tuple[
            OperationalEvent,
            ...,
        ],
    ) -> None:
        if not isinstance(
            operational_events,
            tuple,
        ):
            raise TypeError(
                "operational_events must be a tuple"
            )

        for event in operational_events:
            if not isinstance(
                event,
                OperationalEvent,
            ):
                raise TypeError(
                    "every operational_events item must "
                    "be an OperationalEvent"
                )

    @staticmethod
    def _validate_command_matches_events(
        *,
        command: ChunkTraceCommand,
        operational_events: tuple[
            OperationalEvent,
            ...,
        ],
    ) -> None:
        for event in operational_events:
            if event.tenant_id != command.tenant_id:
                raise ValueError(
                    "OperationalEvent tenant_id does not "
                    "match the command"
                )

            if event.trace_id != command.trace_id:
                raise ValueError(
                    "OperationalEvent trace_id does not "
                    "match the command"
                )

            if event.testcase_id != command.testcase_id:
                raise ValueError(
                    "OperationalEvent testcase_id does not "
                    "match the command"
                )
