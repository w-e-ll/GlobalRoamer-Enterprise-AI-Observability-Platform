from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from globalroamer_platform.application.traces.parse_trace import ParseTrace
from globalroamer_platform.domain.models.mapping_definition import (
    MappingConfiguration,
)
from globalroamer_platform.domain.services.evidence_extractor import (
    EvidenceExtractor,
)
from globalroamer_platform.domain.services.mapping_engine import MappingEngine
from globalroamer_platform.domain.services.signal_extractor import (
    SignalExtractor,
)
from globalroamer_platform.domain.services.time_normalizer import (
    NaiveDatetimeStrategy,
    TimeNormalizer,
)
from globalroamer_platform.domain.services.trace_parser import TraceParser
from globalroamer_platform.domain.services.trace_value_extractor import (
    TraceValueExtractor,
)


@dataclass(frozen=True, slots=True)
class TraceParsingSettings:
    """
    Configuration required to construct the trace parsing pipeline.

    The bootstrap layer translates application configuration into concrete
    domain and infrastructure dependencies.
    """

    mapping_configuration_path: Path
    source_timezone: str = "UTC"
    target_timezone: str = "UTC"
    naive_datetime_strategy: NaiveDatetimeStrategy = (
        NaiveDatetimeStrategy.ASSUME_SOURCE_TIMEZONE
    )

    def __post_init__(self) -> None:
        mapping_path = Path(
            self.mapping_configuration_path
        )

        if not str(mapping_path).strip():
            raise ValueError(
                "mapping_configuration_path must not be empty"
            )

        object.__setattr__(
            self,
            "mapping_configuration_path",
            mapping_path,
        )


@dataclass(frozen=True, slots=True)
class TraceParsingContainer:
    """
    Dependencies composing the executable trace parsing subsystem.

    Keeping concrete dependencies available is useful for:

    - application startup validation;
    - worker construction;
    - API dependency injection;
    - integration testing;
    - health and diagnostics.
    """

    parse_trace: ParseTrace
    parser: TraceParser
    mapping_configuration_provider: Any
    time_normalizer: TimeNormalizer
    evidence_extractor: EvidenceExtractor
    signal_extractor: SignalExtractor
    value_extractor: TraceValueExtractor
    mapping_engine: MappingEngine


def build_trace_parsing_container(
    *,
    settings: TraceParsingSettings,
    parser: TraceParser | None = None,
    mapping_configuration_provider: Any | None = None,
) -> TraceParsingContainer:
    """
    Construct the complete trace parsing subsystem.

    Optional parser and mapping-provider arguments allow integration tests
    to replace infrastructure dependencies without changing the use case.

    The default mapping provider is imported lazily because it belongs to
    the infrastructure layer and may require YAML-specific dependencies.
    """

    concrete_parser = parser or TraceParser()

    concrete_mapping_provider = (
        mapping_configuration_provider
        or _build_yaml_mapping_provider(
            settings.mapping_configuration_path
        )
    )

    time_normalizer = TimeNormalizer(
        source_timezone=settings.source_timezone,
        target_timezone=settings.target_timezone,
        naive_strategy=settings.naive_datetime_strategy,
    )

    evidence_extractor = EvidenceExtractor()
    signal_extractor = SignalExtractor()
    value_extractor = TraceValueExtractor()
    mapping_engine = MappingEngine()

    parse_trace = ParseTrace(
        parser=concrete_parser,
        mapping_configuration_provider=(
            concrete_mapping_provider
        ),
        time_normalizer=time_normalizer,
        evidence_extractor=evidence_extractor,
        signal_extractor=signal_extractor,
        value_extractor=value_extractor,
        mapping_engine=mapping_engine,
    )

    return TraceParsingContainer(
        parse_trace=parse_trace,
        parser=concrete_parser,
        mapping_configuration_provider=(
            concrete_mapping_provider
        ),
        time_normalizer=time_normalizer,
        evidence_extractor=evidence_extractor,
        signal_extractor=signal_extractor,
        value_extractor=value_extractor,
        mapping_engine=mapping_engine,
    )


def build_parse_trace(
    *,
    settings: TraceParsingSettings,
    parser: TraceParser | None = None,
    mapping_configuration_provider: Any | None = None,
) -> ParseTrace:
    """
    Convenience factory for callers that only require the use case.
    """

    container = build_trace_parsing_container(
        settings=settings,
        parser=parser,
        mapping_configuration_provider=(
            mapping_configuration_provider
        ),
    )

    return container.parse_trace


def validate_trace_parsing_configuration(
    container: TraceParsingContainer,
) -> MappingConfiguration:
    """
    Load and validate mapping configuration during application startup.

    Calling this function at startup ensures that malformed or missing YAML
    configuration fails before the API or worker begins accepting work.
    """

    configuration = (
        container.mapping_configuration_provider
        .get_configuration()
    )

    if not isinstance(
        configuration,
        MappingConfiguration,
    ):
        raise TypeError(
            "Mapping configuration provider returned "
            f"{type(configuration).__name__}; "
            "expected MappingConfiguration"
        )

    return configuration


def _build_yaml_mapping_provider(
    mapping_configuration_path: Path,
) -> Any:
    """
    Construct the infrastructure YAML provider lazily.

    The provider file is the next infrastructure component to implement.
    """

    try:
        from globalroamer_platform.infrastructure.configuration.yaml_mapping_provider import (
            YamlMappingConfigurationProvider,
        )
    except ImportError as exc:
        raise RuntimeError(
            "YamlMappingConfigurationProvider is not available. "
            "Create "
            "'globalroamer_platform/infrastructure/"
            "configuration/yaml_mapping_provider.py'."
        ) from exc

    return YamlMappingConfigurationProvider(
        path=mapping_configuration_path
    )
