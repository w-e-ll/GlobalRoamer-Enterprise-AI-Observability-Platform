# globalroamer_platform/telemetry/metrics.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fastapi import FastAPI, Response
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)
from prometheus_client.exposition import CONTENT_TYPE_LATEST

from globalroamer_platform.core.config import MetricsSettings


HTTP_DURATION_BUCKETS: Final[tuple[float, ...]] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


@dataclass(frozen=True, slots=True)
class PlatformMetrics:
    """Prometheus metrics exposed by the platform."""

    registry: CollectorRegistry

    http_requests_total: Counter
    http_request_duration_seconds: Histogram
    http_requests_in_progress: Gauge

    database_health: Gauge
    application_info: Info

    trace_stage_total: Counter
    trace_stage_duration_seconds: Histogram
    trace_processing_failures_total: Counter


_metrics: PlatformMetrics | None = None
_metrics_settings: MetricsSettings | None = None


def configure_metrics(
    settings: MetricsSettings,
    *,
    app_name: str,
    environment: str,
    version: str = "0.1.0",
) -> PlatformMetrics | None:
    """
    Configure the platform Prometheus metrics.

    Returns None when metrics are disabled. Repeated calls with the same
    settings return the existing metrics instance.
    """

    global _metrics
    global _metrics_settings

    if not settings.enabled:
        return None

    if _metrics is not None:
        if _metrics_settings != settings:
            raise RuntimeError(
                "Prometheus metrics were already configured "
                "with different settings"
            )

        return _metrics

    registry = CollectorRegistry()

    http_requests_total = Counter(
        name="http_requests_total",
        documentation=(
            "Total number of HTTP requests processed by the API."
        ),
        labelnames=(
            "method",
            "route",
            "status_code",
        ),
        namespace=settings.namespace,
        subsystem=settings.subsystem,
        registry=registry,
    )

    http_request_duration_seconds = Histogram(
        name="http_request_duration_seconds",
        documentation=(
            "HTTP request processing duration in seconds."
        ),
        labelnames=(
            "method",
            "route",
        ),
        buckets=HTTP_DURATION_BUCKETS,
        namespace=settings.namespace,
        subsystem=settings.subsystem,
        registry=registry,
    )

    http_requests_in_progress = Gauge(
        name="http_requests_in_progress",
        documentation=(
            "Number of HTTP requests currently being processed."
        ),
        labelnames=(
            "method",
            "route",
        ),
        namespace=settings.namespace,
        subsystem=settings.subsystem,
        registry=registry,
    )

    database_health = Gauge(
        name="database_health",
        documentation=(
            "Database availability status: 1 for healthy, "
            "0 for unhealthy."
        ),
        namespace=settings.namespace,
        subsystem=settings.subsystem,
        registry=registry,
    )

    application_info = Info(
        name="application",
        documentation=(
            "Static information about the running application."
        ),
        namespace=settings.namespace,
        subsystem=settings.subsystem,
        registry=registry,
    )

    trace_stage_total = Counter(
        name="trace_stage_total",
        documentation=(
            "Total number of trace-processing stage executions."
        ),
        labelnames=(
            "stage",
            "result",
        ),
        namespace=settings.namespace,
        subsystem=settings.subsystem,
        registry=registry,
    )

    trace_stage_duration_seconds = Histogram(
        name="trace_stage_duration_seconds",
        documentation=(
            "Trace-processing stage duration in seconds."
        ),
        labelnames=("stage",),
        buckets=HTTP_DURATION_BUCKETS,
        namespace=settings.namespace,
        subsystem=settings.subsystem,
        registry=registry,
    )

    trace_processing_failures_total = Counter(
        name="trace_processing_failures_total",
        documentation=(
            "Total number of trace-processing failures."
        ),
        labelnames=(
            "stage",
            "error_type",
        ),
        namespace=settings.namespace,
        subsystem=settings.subsystem,
        registry=registry,
    )

    application_info.info(
        {
            "name": app_name,
            "environment": environment,
            "version": version,
        }
    )

    _metrics = PlatformMetrics(
        registry=registry,
        http_requests_total=http_requests_total,
        http_request_duration_seconds=(
            http_request_duration_seconds
        ),
        http_requests_in_progress=http_requests_in_progress,
        database_health=database_health,
        application_info=application_info,
        trace_stage_total=trace_stage_total,
        trace_stage_duration_seconds=(
            trace_stage_duration_seconds
        ),
        trace_processing_failures_total=(
            trace_processing_failures_total
        ),
    )
    _metrics_settings = settings

    return _metrics


def get_metrics() -> PlatformMetrics | None:
    """
    Return the configured platform metrics.

    Returns None when metrics are disabled or have not been configured.
    """

    return _metrics


def set_database_health(
    healthy: bool,
) -> None:
    """Update the database health gauge when metrics are enabled."""

    metrics = get_metrics()

    if metrics is None:
        return

    metrics.database_health.set(
        1 if healthy else 0
    )


def register_metrics_endpoint(
    app: FastAPI,
    settings: MetricsSettings,
) -> None:
    """Register the Prometheus metrics endpoint."""

    if not settings.enabled:
        return

    metrics = get_metrics()

    if metrics is None:
        raise RuntimeError(
            "Metrics must be configured before registering "
            "the metrics endpoint"
        )

    async def metrics_endpoint() -> Response:
        payload = generate_latest(
            metrics.registry
        )

        return Response(
            content=payload,
            media_type=CONTENT_TYPE_LATEST,
        )

    app.add_api_route(
        path=settings.endpoint_path,
        endpoint=metrics_endpoint,
        methods=["GET"],
        include_in_schema=settings.include_in_schema,
        name="prometheus_metrics",
    )


def reset_metrics_for_testing() -> None:
    """
    Reset the metrics singleton.

    This function is intended only for isolated automated tests.
    """

    global _metrics
    global _metrics_settings

    _metrics = None
    _metrics_settings = None
