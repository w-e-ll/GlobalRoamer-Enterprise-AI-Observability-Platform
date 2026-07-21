"""One-shot runtime for the parser worker.

This module creates a TRACE_ARTIFACT_RECEIVED event from command-line
arguments, runs ParserWorker, and commits the parsed trace and transactional
outbox message in one database transaction.

A broker-backed consumer loop can later reuse the same transaction logic.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from globalroamer_platform.bootstrap.parser_worker import (
    build_parser_worker,
)
from globalroamer_platform.domain.events.event_envelope import (
    EventEnvelope,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_ARTIFACT_RECEIVED,
)
from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
)


LOGGER = logging.getLogger(__name__)


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the parser-worker command-line argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Process one trace artifact through ParserWorker and "
            "atomically persist the parsed trace and outgoing "
            "transactional outbox message."
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
        help="Tenant identifier.",
    )

    parser.add_argument(
        "--trace-id",
        default=None,
        help=(
            "Trace identifier. Defaults to the source "
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
        "--correlation-id",
        default=None,
        help=(
            "Optional correlation identifier. A UUID is "
            "generated when omitted."
        ),
    )

    parser.add_argument(
        "--source-timezone",
        default="UTC",
        help="Timezone assigned to source timestamps.",
    )

    parser.add_argument(
        "--target-timezone",
        default="UTC",
        help="Timezone used for normalized timestamps.",
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


async def run_parser_worker(
    arguments: argparse.Namespace,
) -> int:
    """Run one parser-worker transaction."""
    trace_path = arguments.trace_path.resolve()
    mapping_path = arguments.mapping.resolve()

    _validate_input_file(
        trace_path,
        description="Trace file",
    )
    _validate_input_file(
        mapping_path,
        description="Mapping configuration",
    )

    if arguments.max_file_size_mb <= 0:
        raise ValueError(
            "max-file-size-mb must be greater than zero"
        )

    tenant_id = arguments.tenant_id.strip()

    if not tenant_id:
        raise ValueError(
            "tenant-id must not be empty"
        )

    trace_id = (
        arguments.trace_id.strip()
        if arguments.trace_id
        else trace_path.stem
    )

    if not trace_id:
        raise ValueError(
            "trace-id must not be empty"
        )

    testcase_id = (
        arguments.testcase_id.strip()
        if arguments.testcase_id
        else trace_id
    )

    correlation_id = (
        arguments.correlation_id.strip()
        if arguments.correlation_id
        else str(uuid4())
    )

    if not correlation_id:
        raise ValueError(
            "correlation-id must not be empty"
        )

    incoming_event = EventEnvelope(
        event_id=uuid4(),
        event_type=TRACE_ARTIFACT_RECEIVED,
        event_version=1,
        correlation_id=correlation_id,
        causation_id=None,
        tenant_id=tenant_id,
        occurred_at=datetime.now(timezone.utc),
        producer="globalroamer.parser-worker-runtime",
        payload={
            "source_path": str(trace_path),
            "trace_id": trace_id,
            "testcase_id": testcase_id,
        },
    )

    LOGGER.info(
        "Parser worker runtime started",
        extra={
            "event_id": str(incoming_event.event_id),
            "event_type": incoming_event.event_type,
            "correlation_id": correlation_id,
            "tenant_id": tenant_id,
            "trace_id": trace_id,
            "testcase_id": testcase_id,
            "source_path": str(trace_path),
            "stage": "runtime.parser",
        },
    )

    async with async_session_factory() as session:
        worker = build_parser_worker(
            session=session,
            trace_directory=trace_path.parent,
            mapping_configuration_path=mapping_path,
            source_timezone=arguments.source_timezone,
            target_timezone=arguments.target_timezone,
            supported_extensions=[
                trace_path.suffix,
            ],
            max_file_size_mb=(
                arguments.max_file_size_mb
            ),
        )

        try:
            outgoing_event = await worker.handle(
                incoming_event
            )

            await session.commit()

        except Exception:
            await session.rollback()

            LOGGER.exception(
                "Parser worker transaction rolled back",
                extra={
                    "event_id": str(
                        incoming_event.event_id
                    ),
                    "correlation_id": correlation_id,
                    "tenant_id": tenant_id,
                    "trace_id": trace_id,
                    "stage": "runtime.parser",
                },
            )

            raise

    LOGGER.info(
        "Parser worker runtime completed",
        extra={
            "event_id": str(incoming_event.event_id),
            "produced_event_id": str(
                outgoing_event.event_id
            ),
            "produced_event_type": (
                outgoing_event.event_type
            ),
            "correlation_id": correlation_id,
            "tenant_id": tenant_id,
            "trace_id": trace_id,
            "stage": "runtime.parser",
        },
    )

    print("\nParser worker result")
    print("=" * 60)
    print(
        f"Incoming event ID:  {incoming_event.event_id}"
    )
    print(
        f"Outgoing event ID:  {outgoing_event.event_id}"
    )
    print(
        f"Outgoing type:      {outgoing_event.event_type}"
    )
    print(
        f"Correlation ID:     {outgoing_event.correlation_id}"
    )
    print(
        f"Causation ID:       {outgoing_event.causation_id}"
    )
    print(
        f"Tenant ID:          {outgoing_event.tenant_id}"
    )
    print(
        f"Trace ID:           "
        f"{outgoing_event.payload['trace_id']}"
    )
    print(
        f"Parsed trace ID:    "
        f"{outgoing_event.payload['parsed_trace_id']}"
    )
    print(
        f"Rows:               "
        f"{outgoing_event.payload['row_count']}"
    )
    print(
        "Transaction:        committed"
    )
    print(
        "Outbox message:     persisted as pending"
    )

    return 0


def _validate_input_file(
    path: Path,
    *,
    description: str,
) -> None:
    """Validate a required local input file."""
    if not path.exists():
        raise FileNotFoundError(
            f"{description} was not found: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"{description} is not a file: {path}"
        )


def configure_logging() -> None:
    """Configure basic console logging for the runtime."""
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
    """Run the parser-worker CLI."""
    configure_logging()

    arguments = build_argument_parser().parse_args(
        argv
    )

    try:
        return asyncio.run(
            run_parser_worker(arguments)
        )

    except KeyboardInterrupt:
        LOGGER.warning(
            "Parser worker runtime interrupted"
        )
        return 130

    except Exception:
        LOGGER.exception(
            "Parser worker runtime failed"
        )
        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )
