from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from globalroamer_platform.domain.models.mapping_definition import (
    MappingConfiguration,
)
from globalroamer_platform.domain.models.parsed_trace import ParsedTrace
from globalroamer_platform.domain.models.raw_trace import RawTrace
from globalroamer_platform.domain.services.evidence_extractor import (
    EvidenceExtractor,
)
from globalroamer_platform.domain.services.mapping_engine import MappingEngine
from globalroamer_platform.domain.services.signal_extractor import (
    SignalExtractor,
)
from globalroamer_platform.domain.services.time_normalizer import (
    TimeNormalizer,
)
from globalroamer_platform.domain.services.trace_value_extractor import (
    TraceValueExtractor,
)


class TraceParserPort(Protocol):
    """
    Application-facing parser contract.

    The concrete implementation may read CSV content from a file,
    object storage, an event payload, or another infrastructure source.
    """

    def parse(self, source: object) -> RawTrace:
        """Parse the source artifact into an immutable RawTrace."""


class MappingConfigurationProvider(Protocol):
    """
    Provide the mapping configuration used for one parsing execution.

    The implementation may load configuration from YAML, a database,
    object storage, or an in-memory application configuration.
    """

    def get_configuration(self) -> MappingConfiguration:
        """Return the active validated mapping configuration."""


@dataclass(frozen=True, slots=True)
class ParseTraceCommand:
    """
    Input for the trace parsing use case.

    `source` remains infrastructure-neutral. Its concrete type is defined
    by the injected TraceParser implementation.
    """

    source: object
    metadata: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ParseTraceResult:
    """Application result returned by the parse-trace use case."""

    parsed_trace: ParsedTrace

    @property
    def is_successful(self) -> bool:
        return self.parsed_trace.is_valid

    @property
    def is_complete(self) -> bool:
        return self.parsed_trace.is_complete


class ParseTrace:
    """
    Orchestrate the complete trace parsing pipeline.

    Execution order:

        source
          ↓
        TraceParser
          ↓
        RawTrace
          ↓
        TimeNormalizer
          ↓
        normalized RawTrace
          ├── EvidenceExtractor
          ├── SignalExtractor
          └── TraceValueExtractor
                       ↓
              ExtractedTraceValues
                       ↓
                 MappingEngine
                       ↓
                MappedTraceValues
                       ↓
                  ParsedTrace

    The use case coordinates domain services but does not contain parsing,
    extraction, mapping, timezone, persistence, or transport logic.
    """

    def __init__(
        self,
        *,
        parser: TraceParserPort,
        mapping_configuration_provider: MappingConfigurationProvider,
        time_normalizer: TimeNormalizer,
        evidence_extractor: EvidenceExtractor,
        signal_extractor: SignalExtractor,
        value_extractor: TraceValueExtractor,
        mapping_engine: MappingEngine,
    ) -> None:
        self._parser = parser
        self._mapping_configuration_provider = (
            mapping_configuration_provider
        )
        self._time_normalizer = time_normalizer
        self._evidence_extractor = evidence_extractor
        self._signal_extractor = signal_extractor
        self._value_extractor = value_extractor
        self._mapping_engine = mapping_engine

    def execute(
        self,
        command: ParseTraceCommand,
    ) -> ParseTraceResult:
        """
        Parse one source artifact and assemble the final domain aggregate.

        Domain-level extraction failures are represented inside the
        resulting models where supported. Unexpected infrastructure or
        programming errors are intentionally allowed to propagate to the
        application boundary.
        """

        raw_trace = self._parser.parse(
            command.source
        )

        normalized_trace_result = (
            self._time_normalizer.normalize_trace(
                raw_trace
            )
        )
        normalized_trace = normalized_trace_result.trace

        evidences = self._evidence_extractor.extract(
            normalized_trace
        )
        signals = self._signal_extractor.extract(
            normalized_trace
        )
        extracted_values = self._value_extractor.extract(
            normalized_trace
        )

        mapping_configuration = (
            self._mapping_configuration_provider.get_configuration()
        )

        mapped_values = self._mapping_engine.map(
            trace=normalized_trace,
            extracted_values=extracted_values,
            configuration=mapping_configuration,
        )

        normalized_mapped_values = (
            self._time_normalizer.normalize_mapped_values(
                mapped_values
            )
        )

        parsed_trace = ParsedTrace.create(
            raw_trace=normalized_trace,
            extracted_values=extracted_values,
            mapped_values=normalized_mapped_values,
            evidences=evidences,
            signals=signals,
            warnings=normalized_trace_result.warnings,
            errors=normalized_trace_result.errors,
            metadata={
                **dict(command.metadata or {}),
                "mapping_configuration_version": (
                    mapping_configuration.version
                ),
                "source_timezone": (
                    self._time_normalizer.source_timezone_name
                ),
                "target_timezone": (
                    self._time_normalizer.target_timezone_name
                ),
            },
        )

        return ParseTraceResult(
            parsed_trace=parsed_trace
        )
