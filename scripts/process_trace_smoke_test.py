from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Sequence

from globalroamer_platform.application.traces.process_trace import (
    ProcessTraceCommand,
)
from globalroamer_platform.bootstrap.trace_parsing import (
    TraceParsingSettings,
    build_trace_parsing_container,
    validate_trace_parsing_configuration,
)
from globalroamer_platform.bootstrap.trace_processing import (
    build_process_trace,
)
from globalroamer_platform.domain.services.time_normalizer import (
    NaiveDatetimeStrategy,
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
            "Execute the complete ProcessTrace application workflow: "
            "load, parse, persist, commit, and verify one trace."
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
            "Path to the trace mapping configuration. "
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
            "Trace identifier. Defaults to the input "
            "filename stem."
        ),
    )

    parser.add_argument(
        "--testcase-id",
        default=None,
        help=(
            "Optional testcase identifier. Defaults to "
            "the trace identifier."
        ),
    )

    parser.add_argument(
        "--source-timezone",
        default="UTC",
        help=(
            "Timezone assigned to source timestamps "
            "without timezone information."
        ),
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
            "Strategy used for source timestamps that "
            "do not contain timezone information."
        ),
    )

    parser.add_argument(
        "--max-file-size-mb",
        type=int,
        default=100,
        help=(
            "Maximum accepted trace file size in MB. "
            "Default: 100"
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

    if arguments.max_file_size_mb <= 0:
        raise ValueError(
            "max-file-size-mb must be greater than zero",
        )

    tenant_id = arguments.tenant_id.strip()

    if not tenant_id:
        raise ValueError(
            "tenant-id must not be empty",
        )

    trace_id = (
        arguments.trace_id.strip()
        if arguments.trace_id
        else trace_path.stem
    )

    if not trace_id:
        raise ValueError(
            "trace-id must not be empty",
        )

    testcase_id = (
        arguments.testcase_id.strip()
        if arguments.testcase_id
        else trace_id
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

    parsing_container = build_trace_parsing_container(
        settings=parsing_settings,
    )

    mapping_configuration = (
        validate_trace_parsing_configuration(
            parsing_container,
        )
    )

    LOGGER.info(
        "Mapping configuration loaded "
        "version=%s definitions=%s",
        mapping_configuration.version,
        len(mapping_configuration.definitions),
    )

    async with async_session_factory() as session:
        process_trace = build_process_trace(
            session=session,
            parse_trace=parsing_container.parse_trace,
            trace_directory=trace_path.parent,
            supported_extensions=[
                trace_path.suffix,
            ],
            max_file_size_mb=(
                arguments.max_file_size_mb
            ),
        )

        try:
            result = await process_trace.execute(
                ProcessTraceCommand(
                    source_path=trace_path,
                    tenant_id=tenant_id,
                    trace_id=trace_id,
                    testcase_id=testcase_id,
                ),
            )

            await session.commit()

        except Exception:
            await session.rollback()
            raise

    LOGGER.info(
        "ProcessTrace workflow completed "
        "database_id=%s tenant_id=%s trace_id=%s",
        result.parsed_trace_id,
        result.tenant_id,
        result.trace_id,
    )

    validate_process_result(
        result=result,
        expected_tenant_id=tenant_id,
        expected_trace_id=trace_id,
        expected_testcase_id=testcase_id,
    )

    loaded_model = await load_persisted_trace(
        tenant_id=tenant_id,
        trace_id=trace_id,
    )

    validate_persisted_model(
        loaded_model=loaded_model,
        result=result,
    )

    print_processing_summary(
        result=result,
        loaded_model=loaded_model,
    )

    LOGGER.info(
        "ProcessTrace smoke test completed successfully",
    )

    return 0


async def load_persisted_trace(
    *,
    tenant_id: str,
    trace_id: str,
) -> object:
    """
    Read the persisted record using a new database session.

    This confirms that the transaction was committed and that the
    record is not only present in the original ORM identity map.
    """

    async with async_session_factory() as session:
        store = ParsedTraceStore(
            session,
        )

        loaded_model = await store.get(
            tenant_id=tenant_id,
            trace_id=trace_id,
        )

    if loaded_model is None:
        raise RuntimeError(
            "ProcessTrace completed, but the persisted trace "
            "could not be read from the database",
        )

    return loaded_model


def validate_process_result(
    *,
    result: object,
    expected_tenant_id: str,
    expected_trace_id: str,
    expected_testcase_id: str | None,
) -> None:
    mismatches: list[str] = []

    expected_values = {
        "tenant_id": expected_tenant_id,
        "trace_id": expected_trace_id,
        "testcase_id": expected_testcase_id,
    }

    for field_name, expected_value in expected_values.items():
        actual_value = getattr(
            result,
            field_name,
        )

        if actual_value != expected_value:
            mismatches.append(
                f"{field_name}: "
                f"expected={expected_value!r}, "
                f"actual={actual_value!r}",
            )

    if result.row_count <= 0:
        mismatches.append(
            "row_count must be greater than zero",
        )

    if result.error_count < 0:
        mismatches.append(
            "error_count must not be negative",
        )

    if result.warning_count < 0:
        mismatches.append(
            "warning_count must not be negative",
        )

    if mismatches:
        raise AssertionError(
            "ProcessTrace result validation failed:\n"
            + "\n".join(
                f"  - {mismatch}"
                for mismatch in mismatches
            ),
        )


def validate_persisted_model(
    *,
    loaded_model: object,
    result: object,
) -> None:
    expected_values = {
        "id": result.parsed_trace_id,
        "tenant_id": result.tenant_id,
        "trace_id": result.trace_id,
        "testcase_id": result.testcase_id,
        "row_count": result.row_count,
        "evidence_count": result.evidence_count,
        "signal_count": result.signal_count,
        "extracted_value_count": (
            result.extracted_value_count
        ),
        "mapped_value_count": (
            result.mapped_value_count
        ),
        "warning_count": result.warning_count,
        "error_count": result.error_count,
        "is_valid": result.is_valid,
        "is_complete": result.is_complete,
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
            "Persisted ProcessTrace validation failed:\n"
            + "\n".join(
                f"  - {mismatch}"
                for mismatch in mismatches
            ),
        )


def print_processing_summary(
    *,
    result: object,
    loaded_model: object,
) -> None:
    print("\nProcessTrace workflow summary")
    print("=" * 60)
    print(
        f"Database ID:         {result.parsed_trace_id}"
    )
    print(
        f"Tenant ID:           {result.tenant_id}"
    )
    print(
        f"Trace ID:            {result.trace_id}"
    )
    print(
        f"Testcase ID:         {result.testcase_id}"
    )
    print(
        f"Rows:                {result.row_count}"
    )
    print(
        f"Evidences:           {result.evidence_count}"
    )
    print(
        f"Signals:             {result.signal_count}"
    )
    print(
        "Extracted values:    "
        f"{result.extracted_value_count}"
    )
    print(
        "Mapped values:       "
        f"{result.mapped_value_count}"
    )
    print(
        f"Warnings:            {result.warning_count}"
    )
    print(
        f"Errors:              {result.error_count}"
    )
    print(
        f"Valid:               {result.is_valid}"
    )
    print(
        f"Complete:            {result.is_complete}"
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
            "ProcessTrace smoke test interrupted",
        )
        return 130

    except Exception:
        LOGGER.exception(
            "ProcessTrace smoke test failed",
        )
        return 1


if __name__ == "__main__":
    sys.exit(
        main(),
    )
