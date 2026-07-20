from __future__ import annotations

from pathlib import Path

from globalroamer_platform.bootstrap.trace_parsing import (
    TraceParsingSettings,
)
from globalroamer_platform.core.config import Settings
from globalroamer_platform.domain.services.time_normalizer import (
    NaiveDatetimeStrategy,
)


def build_trace_parsing_settings(
    settings: Settings,
) -> TraceParsingSettings:
    return TraceParsingSettings(
        mapping_configuration_path=Path(
            settings.trace_mapping_configuration_path
        ),
        source_timezone=settings.trace_source_timezone,
        target_timezone=settings.trace_target_timezone,
        naive_datetime_strategy=NaiveDatetimeStrategy(
            settings.trace_naive_datetime_strategy
        ),
    )
