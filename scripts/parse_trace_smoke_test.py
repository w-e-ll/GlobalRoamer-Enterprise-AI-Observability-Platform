from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Sequence

from globalroamer_platform.application.traces.parse_trace import (
    ParseTraceCommand,
)
from globalroamer_platform.bootstrap.trace_parsing import (
    TraceParsingSettings,
    build_trace_parsing_container,
    validate_trace_parsing_configuration,
)
from globalroamer_platform.domain.models.parsed_trace import ParsedTrace
from globalroamer_platform.domain.services.time_normalizer import (
    NaiveDatetimeStrategy,
)
from globalroamer_platform.domain.services.trace_loader import TraceLoader


LOGGER = logging.getLogger(__name__)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the GlobalRoamer trace parsing pipeline "
            "against one local trace file."
        )
    )

    parser.add_argument(
        "trace_path",
        type=Path,
        help="Path to the CSV trace file.",
    )

    parser.add_argument(
        "--mapping",
        type=Path,
        default=Path("etc/trace_mapping.yml"),
        help=(
            "Path to the trace mapping configuration. "
            "Default: etc/trace_mapping.yml"
        ),
    )

    parser.add_argument(
        "--source-timezone",
        default="UTC",
        help="Timezone assigned to naive source timestamps.",
    )

    parser.add_argument(
        "--target-timezone",
        default="UTC",
        help="Timezone used for normalized timestamps.",
    )

    parser.add_argument(
        "--naive-strategy",
        choices=[
            strategy.value
            for strategy in NaiveDatetimeStrategy
        ],
        default=(
            NaiveDatetimeStrategy
            .ASSUME_SOURCE_TIMEZONE
            .value
        ),
        help=(
            "How timestamps without timezone information "
            "are handled."
        ),
    )

    parser.add_argument(
        "--tenant-id",
        default="smoke-test",
        help="Tenant identifier added to parsing metadata.",
    )

    parser.add_argument(
        "--trace-id",
        default=None,
        help=(
            "Trace identifier added to parsing metadata. "
            "Defaults to the input filename stem."
        ),
    )

    parser.add_argument(
        "--testcase-id",
        default=None,
        help=(
            "Test case identifier assigned to the source artifact. "
            "Defaults to the trace identifier."
        ),
    )

    parser.add_argument(
        "--full-json",
        action="store_true",
        help="Include raw trace rows in JSON output.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Optional path where the parsed JSON result "
            "is written."
        ),
    )

    return parser


def main(
    argv: Sequence[str] | None = None,
) -> int:
    configure_logging()

    arguments = build_argument_parser().parse_args(
        argv
    )

    trace_path = arguments.trace_path.resolve()
    mapping_path = arguments.mapping.resolve()

    try:
        validate_input_file(
            trace_path,
            description="Trace file",
        )
        validate_input_file(
            mapping_path,
            description="Mapping configuration",
        )

        settings = TraceParsingSettings(
            mapping_configuration_path=mapping_path,
            source_timezone=arguments.source_timezone,
            target_timezone=arguments.target_timezone,
            naive_datetime_strategy=(
                NaiveDatetimeStrategy(
                    arguments.naive_strategy
                )
            ),
        )

        container = build_trace_parsing_container(
            settings=settings
        )

        mapping_configuration = (
            validate_trace_parsing_configuration(
                container
            )
        )

        LOGGER.info(
            "Mapping configuration loaded "
            "version=%s definitions=%s",
            mapping_configuration.version,
            len(mapping_configuration.definitions),
        )

        trace_id = (
            arguments.trace_id
            or trace_path.stem
        )

        testcase_id = (
            arguments.testcase_id
            or trace_id
        )

        trace_loader = TraceLoader(
            trace_directory=trace_path.parent,
            supported_extensions=[
                trace_path.suffix,
            ],
            max_file_size_mb=100,
        )

        source_artifact = trace_loader.load(
            trace_path,
            tenant_id=arguments.tenant_id,
            trace_id=trace_id,
            testcase_id=testcase_id,
        )

        LOGGER.info(
            "Source artifact loaded "
            "trace_id=%s testcase_id=%s file=%s size_bytes=%s",
            trace_id,
            testcase_id,
            source_artifact.filename,
            source_artifact.size_bytes,
        )

        result = container.parse_trace.execute(
            ParseTraceCommand(
                source=source_artifact,
                metadata={
                    "tenant_id": arguments.tenant_id,
                    "trace_id": trace_id,
                    "testcase_id": testcase_id,
                    "smoke_test": True,
                    "input_file": trace_path.name,
                },
            )
        )

        parsed_trace = result.parsed_trace

        print_summary(
            parsed_trace=parsed_trace,
            mapping_version=(
                mapping_configuration.version
            ),
        )

        serialized_result = parsed_trace.to_dict(
            include_raw_rows=arguments.full_json
        )

        rendered_json = json.dumps(
            serialized_result,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

        if arguments.output is not None:
            output_path = arguments.output.resolve()

            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            output_path.write_text(
                rendered_json + "\n",
                encoding="utf-8",
            )

            print(
                f"\nJSON output written to: {output_path}"
            )
        else:
            print("\nParsed result:")
            print(rendered_json)

        if not result.is_successful:
            LOGGER.error(
                "Smoke test completed with parsing errors"
            )
            return 2

        LOGGER.info(
            "Trace parsing smoke test completed successfully"
        )

        return 0

    except Exception:
        LOGGER.exception(
            "Trace parsing smoke test failed"
        )

        return 1


def validate_input_file(
    path: Path,
    *,
    description: str,
) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"{description} was not found: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"{description} is not a file: {path}"
        )


def print_summary(
    *,
    parsed_trace: ParsedTrace,
    mapping_version: str,
) -> None:
    print("\nTrace parsing summary")
    print("=" * 60)

    print(
        f"Source:             {parsed_trace.source}"
    )
    print(
        f"Mapping version:    {mapping_version}"
    )
    print(
        f"Rows:               {parsed_trace.row_count}"
    )
    print(
        "Extracted values:   "
        f"{parsed_trace.extracted_value_count}"
    )
    print(
        "Mapped values:      "
        f"{parsed_trace.mapped_value_count}"
    )
    print(
        f"Evidences:          {parsed_trace.evidence_count}"
    )
    print(
        f"Signals:            {parsed_trace.signal_count}"
    )
    print(
        f"Started at:         {parsed_trace.started_at}"
    )
    print(
        f"Ended at:           {parsed_trace.ended_at}"
    )
    print(
        "Duration seconds:   "
        f"{parsed_trace.duration_seconds}"
    )
    print(
        f"Warnings:           {len(parsed_trace.warnings)}"
    )
    print(
        f"Errors:             {len(parsed_trace.errors)}"
    )
    print(
        f"Valid:              {parsed_trace.is_valid}"
    )
    print(
        f"Complete:           {parsed_trace.is_complete}"
    )

    if parsed_trace.warnings:
        print("\nWarnings:")

        for warning in parsed_trace.warnings:
            print(
                f"  - {warning}"
            )

    if parsed_trace.errors:
        print("\nErrors:")

        for error in parsed_trace.errors:
            print(
                f"  - {error}"
            )


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s "
            "%(levelname)s "
            "%(name)s "
            "%(message)s"
        ),
    )


if __name__ == "__main__":
    sys.exit(
        main()
    )
