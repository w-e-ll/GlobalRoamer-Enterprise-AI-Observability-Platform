from __future__ import annotations

import argparse
import asyncio
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
from globalroamer_platform.domain.services.time_normalizer import (
    NaiveDatetimeStrategy,
)
from globalroamer_platform.domain.services.trace_loader import (
    TraceLoader,
)
from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)
from globalroamer_platform.infrastructure.persistence.parsed_trace_store import (
    ParsedTraceStore,
)


LOGGER = logging.getLogger(__name__)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Parse a local trace, persist the ParsedTrace snapshot "
            "in PostgreSQL, and read it back."
        ),
    )

    parser.add_argument(
        "trace_path",
        type=Path,
        help="Path to the source trace file.",
    )

    parser.add_argument(
        "--mapping",
        type=Path,
        default=Path("etc/trace_mapping.yml"),
        help=(
            "Path to the mapping configuration. "
            "Default: etc/trace_mapping.yml"
        ),
    )

    parser.add_argument(
        "--tenant-id",
        default="smoke-test",
        help="Tenant identifier used for persistence.",
    )

    parser.add_argument(
        "--trace-id",
        default=None,
        help=(
            "Trace identifier used for persistence. "
            "Defaults to the input filename stem."
        ),
    )

    parser.add_argument(
        "--testcase-id",
        default=None,
        help=(
            "Optional testcase identifier. "
            "Defaults to the trace identifier."
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

    return parser


async def run_smoke_test(
    arguments: argparse.Namespace,
) -> int:
    trace_path = arguments.trace_path.resolve()
    mapping_path = arguments.mapping.resolve()

    validate_input_file(
        trace_path,
        description="Trace file",
    )
    validate_input_file(
        mapping_path,
        description="Mapping configuration",
    )

    trace_id = (
        arguments.trace_id
        or trace_path.stem
    )

    testcase_id = (
        arguments.testcase_id
        or trace_id
    )

    parsing_settings = TraceParsingSettings(
        mapping_configuration_path=mapping_path,
        source_timezone=arguments.source_timezone,
        target_timezone=arguments.target_timezone,
        naive_datetime_strategy=(
            NaiveDatetimeStrategy(
                arguments.naive_strategy,
            )
        ),
    )

    container = build_trace_parsing_container(
        settings=parsing_settings,
    )

    mapping_configuration = (
        validate_trace_parsing_configuration(
            container,
        )
    )

    LOGGER.info(
        "Mapping configuration loaded "
        "version=%s definitions=%s",
        mapping_configuration.version,
        len(mapping_configuration.definitions),
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

    parse_result = container.parse_trace.execute(
        ParseTraceCommand(
            source=source_artifact,
            metadata={
                "tenant_id": arguments.tenant_id,
                "trace_id": trace_id,
                "testcase_id": testcase_id,
                "smoke_test": True,
                "input_file": trace_path.name,
            },
        ),
    )

    parsed_trace = parse_result.parsed_trace

    if not parse_result.is_successful:
        LOGGER.error(
            "Trace parsing completed with errors: %s",
            parsed_trace.errors,
        )
        return 2

    LOGGER.info(
        "Trace parsed successfully "
        "tenant_id=%s trace_id=%s rows=%s",
        arguments.tenant_id,
        trace_id,
        parsed_trace.row_count,
    )

    async with async_session_factory() as session:
        store = ParsedTraceStore(session)

        try:
            stored_model = await store.save(
                parsed_trace,
            )

            await session.commit()

            LOGGER.info(
                "Parsed trace persisted "
                "database_id=%s tenant_id=%s trace_id=%s",
                stored_model.id,
                stored_model.tenant_id,
                stored_model.trace_id,
            )

        except Exception:
            await session.rollback()
            raise

    # Use a new database session so this verifies an actual database read,
    # not only the ORM identity map from the save operation.
    async with async_session_factory() as session:
        store = ParsedTraceStore(session)

        loaded_model = await store.get(
            tenant_id=arguments.tenant_id,
            trace_id=trace_id,
        )

    if loaded_model is None:
        raise RuntimeError(
            "Parsed trace was saved but could not be read back",
        )

    validate_persisted_model(
        loaded_model=loaded_model,
        parsed_trace=parsed_trace,
    )

    print_persistence_summary(
        loaded_model=loaded_model,
    )

    LOGGER.info(
        "ParsedTraceStore smoke test completed successfully",
    )

    return 0


def validate_persisted_model(
    *,
    loaded_model: object,
    parsed_trace: object,
) -> None:
    metadata = parsed_trace.metadata

    expected_values = {
        "tenant_id": metadata["tenant_id"],
        "trace_id": metadata["trace_id"],
        "testcase_id": metadata.get("testcase_id"),
        "row_count": parsed_trace.row_count,
        "evidence_count": parsed_trace.evidence_count,
        "signal_count": parsed_trace.signal_count,
        "extracted_value_count": (
            parsed_trace.extracted_value_count
        ),
        "mapped_value_count": (
            parsed_trace.mapped_value_count
        ),
        "warning_count": len(parsed_trace.warnings),
        "error_count": len(parsed_trace.errors),
        "is_valid": parsed_trace.is_valid,
        "is_complete": parsed_trace.is_complete,
    }

    mismatches: list[str] = []

    for field_name, expected_value in expected_values.items():
        actual_value = getattr(
            loaded_model,
            field_name,
        )

        if actual_value != expected_value:
            mismatches.append(
                f"{field_name}: "
                f"expected={expected_value!r}, "
                f"actual={actual_value!r}",
            )

    if not isinstance(
        loaded_model.parsed_trace_json,
        dict,
    ):
        mismatches.append(
            "parsed_trace_json is not a dictionary",
        )

    if mismatches:
        raise AssertionError(
            "Persisted ParsedTrace validation failed:\n"
            + "\n".join(
                f"  - {mismatch}"
                for mismatch in mismatches
            ),
        )


def print_persistence_summary(
    *,
    loaded_model: object,
) -> None:
    print("\nParsedTrace persistence summary")
    print("=" * 60)
    print(
        f"Database ID:         {loaded_model.id}"
    )
    print(
        f"Tenant ID:           {loaded_model.tenant_id}"
    )
    print(
        f"Trace ID:            {loaded_model.trace_id}"
    )
    print(
        f"Testcase ID:         {loaded_model.testcase_id}"
    )
    print(
        f"Rows:                {loaded_model.row_count}"
    )
    print(
        f"Evidences:           {loaded_model.evidence_count}"
    )
    print(
        f"Signals:             {loaded_model.signal_count}"
    )
    print(
        "Extracted values:    "
        f"{loaded_model.extracted_value_count}"
    )
    print(
        "Mapped values:       "
        f"{loaded_model.mapped_value_count}"
    )
    print(
        f"Warnings:            {loaded_model.warning_count}"
    )
    print(
        f"Errors:              {loaded_model.error_count}"
    )
    print(
        f"Started at:          {loaded_model.started_at}"
    )
    print(
        f"Ended at:            {loaded_model.ended_at}"
    )
    print(
        "Duration seconds:    "
        f"{loaded_model.duration_seconds}"
    )
    print(
        f"Valid:               {loaded_model.is_valid}"
    )
    print(
        f"Complete:            {loaded_model.is_complete}"
    )
    print(
        f"Created at:          {loaded_model.created_at}"
    )
    print(
        f"Updated at:          {loaded_model.updated_at}"
    )
    print(
        "JSON payload keys:   "
        f"{sorted(loaded_model.parsed_trace_json.keys())}"
    )


def validate_input_file(
    path: Path,
    *,
    description: str,
) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"{description} was not found: {path}",
        )

    if not path.is_file():
        raise ValueError(
            f"{description} is not a file: {path}",
        )


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s %(levelname)s "
            "%(name)s %(message)s"
        ),
    )


def main(
    argv: Sequence[str] | None = None,
) -> int:
    configure_logging()

    arguments = build_argument_parser().parse_args(
        argv,
    )

    try:
        return asyncio.run(
            run_smoke_test(
                arguments,
            ),
        )

    except KeyboardInterrupt:
        LOGGER.warning(
            "ParsedTraceStore smoke test interrupted",
        )
        return 130

    except Exception:
        LOGGER.exception(
            "ParsedTraceStore smoke test failed",
        )
        return 1


if __name__ == "__main__":
    sys.exit(
        main(),
    )
