# globalroamer_platform/application/workflows/load_trace.py

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from globalroamer_platform.core.logging import (
    stage_context,
    tenant_id_context,
    trace_id_context,
)
from globalroamer_platform.domain.models.source_artifact import (
    SourceArtifact,
)
from globalroamer_platform.domain.services.trace_loader import (
    TraceLoader,
)
from globalroamer_platform.telemetry.metrics import (
    get_metrics,
)
from globalroamer_platform.telemetry.tracing import (
    get_tracer,
)


logger = logging.getLogger(__name__)

WORKFLOW_STAGE = "trace_loading"


@dataclass(frozen=True, slots=True)
class LoadTraceCommand:
    """Input required to load one trace source."""

    source_path: Path

    tenant_id: str | None = None
    trace_id: str | None = None
    testcase_id: str | None = None


@dataclass(frozen=True, slots=True)
class LoadTraceResult:
    """Result of a successful trace-loading workflow."""

    artifact: SourceArtifact
    duration_seconds: float


class LoadTraceWorkflow:
    """
    Orchestrate loading and validation of one trace source.

    Filesystem work remains inside TraceLoader. This workflow provides
    application-level logging, contextual propagation, metrics and
    distributed tracing.
    """

    def __init__(
        self,
        *,
        trace_loader: TraceLoader,
    ) -> None:
        self._trace_loader = trace_loader
        self._tracer = get_tracer(__name__)

    async def execute(
        self,
        command: LoadTraceCommand,
    ) -> LoadTraceResult:
        """
        Load one trace and return its immutable source metadata.

        The synchronous filesystem loader runs in a worker thread so
        the FastAPI event loop is not blocked by file access and
        checksum calculation.
        """

        tenant_token = tenant_id_context.set(
            command.tenant_id or "-"
        )
        trace_token = trace_id_context.set(
            command.trace_id or "-"
        )
        stage_token = stage_context.set(
            WORKFLOW_STAGE
        )

        started_at = perf_counter()
        metrics = get_metrics()

        logger.info(
            "Load trace workflow started source_path=%s "
            "testcase_id=%s",
            command.source_path,
            command.testcase_id or "-",
        )

        try:
            with self._tracer.start_as_current_span(
                "load_trace"
            ) as span:
                span.set_attribute(
                    "globalroamer.stage",
                    WORKFLOW_STAGE,
                )
                span.set_attribute(
                    "globalroamer.source_path",
                    str(command.source_path),
                )

                if command.tenant_id is not None:
                    span.set_attribute(
                        "globalroamer.tenant_id",
                        command.tenant_id,
                    )

                if command.trace_id is not None:
                    span.set_attribute(
                        "globalroamer.business_trace_id",
                        command.trace_id,
                    )

                if command.testcase_id is not None:
                    span.set_attribute(
                        "globalroamer.testcase_id",
                        command.testcase_id,
                    )

                artifact = await asyncio.to_thread(
                    self._trace_loader.load,
                    command.source_path,
                    tenant_id=command.tenant_id,
                    trace_id=command.trace_id,
                    testcase_id=command.testcase_id,
                )

                span.set_attribute(
                    "globalroamer.artifact_id",
                    str(artifact.id),
                )
                span.set_attribute(
                    "globalroamer.artifact_size_bytes",
                    artifact.size_bytes,
                )
                span.set_attribute(
                    "globalroamer.artifact_extension",
                    artifact.extension,
                )
                span.set_attribute(
                    "globalroamer.artifact_checksum_sha256",
                    artifact.checksum_sha256,
                )

            duration_seconds = (
                perf_counter() - started_at
            )

            if metrics is not None:
                metrics.trace_stage_total.labels(
                    stage=WORKFLOW_STAGE,
                    result="success",
                ).inc()

                metrics.trace_stage_duration_seconds.labels(
                    stage=WORKFLOW_STAGE,
                ).observe(
                    duration_seconds
                )

            logger.info(
                "Load trace workflow completed "
                "artifact_id=%s source_path=%s "
                "size_bytes=%d duration_ms=%.2f",
                artifact.id,
                artifact.source_path,
                artifact.size_bytes,
                duration_seconds * 1000,
            )

            return LoadTraceResult(
                artifact=artifact,
                duration_seconds=duration_seconds,
            )

        except Exception as exc:
            duration_seconds = (
                perf_counter() - started_at
            )

            if metrics is not None:
                metrics.trace_stage_total.labels(
                    stage=WORKFLOW_STAGE,
                    result="failure",
                ).inc()

                metrics.trace_stage_duration_seconds.labels(
                    stage=WORKFLOW_STAGE,
                ).observe(
                    duration_seconds
                )

                metrics.trace_processing_failures_total.labels(
                    stage=WORKFLOW_STAGE,
                    error_type=type(exc).__name__,
                ).inc()

            logger.exception(
                "Load trace workflow failed source_path=%s "
                "duration_ms=%.2f",
                command.source_path,
                duration_seconds * 1000,
            )

            raise

        finally:
            stage_context.reset(
                stage_token
            )
            trace_id_context.reset(
                trace_token
            )
            tenant_id_context.reset(
                tenant_token
            )
