# globalroamer_platform/api/middleware/request_logging.py

from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.routing import Match

from globalroamer_platform.core.logging import (
    correlation_id_context,
)
from globalroamer_platform.telemetry.metrics import (
    get_metrics,
)


logger = logging.getLogger(__name__)


UNKNOWN_ROUTE = "unknown"

QUIET_PATHS = {
    "/live",
    "/metrics",
}


def register_request_logging(app: FastAPI) -> None:
    """
    Register HTTP request logging and Prometheus metrics middleware.

    The middleware:

    - assigns or propagates a correlation ID;
    - logs request start, completion and failure;
    - suppresses successful logs for high-frequency operational paths;
    - always logs request failures;
    - returns the correlation ID in the response;
    - records HTTP request count, duration and concurrency metrics.
    """

    @app.middleware("http")
    async def request_logging_middleware(
        request: Request,
        call_next,
    ):
        correlation_id = (
            request.headers.get("X-Correlation-ID")
            or str(uuid4())
        )

        correlation_token = correlation_id_context.set(
            correlation_id
        )

        started_at = perf_counter()
        metrics = get_metrics()

        method = request.method
        path = request.url.path
        should_log = path not in QUIET_PATHS

        initial_route = _resolve_route_template(
            request=request,
            app=app,
        )

        in_progress_metric = None

        if metrics is not None:
            in_progress_metric = (
                metrics.http_requests_in_progress.labels(
                    method=method,
                    route=initial_route,
                )
            )
            in_progress_metric.inc()

        if should_log:
            logger.info(
                "HTTP request started method=%s path=%s",
                method,
                path,
            )

        try:
            response = await call_next(request)

            duration_seconds = (
                perf_counter() - started_at
            )

            route = _resolve_route_template(
                request=request,
                app=app,
            )

            if should_log:
                logger.info(
                    "HTTP request completed method=%s path=%s "
                    "status_code=%d duration_ms=%.2f",
                    method,
                    path,
                    response.status_code,
                    duration_seconds * 1000,
                )

            if metrics is not None:
                metrics.http_requests_total.labels(
                    method=method,
                    route=route,
                    status_code=str(
                        response.status_code
                    ),
                ).inc()

                metrics.http_request_duration_seconds.labels(
                    method=method,
                    route=route,
                ).observe(
                    duration_seconds
                )

            response.headers["X-Correlation-ID"] = (
                correlation_id
            )

            return response

        except Exception:
            duration_seconds = (
                perf_counter() - started_at
            )

            route = _resolve_route_template(
                request=request,
                app=app,
            )

            logger.exception(
                "HTTP request failed method=%s path=%s "
                "duration_ms=%.2f",
                method,
                path,
                duration_seconds * 1000,
            )

            if metrics is not None:
                metrics.http_requests_total.labels(
                    method=method,
                    route=route,
                    status_code="500",
                ).inc()

                metrics.http_request_duration_seconds.labels(
                    method=method,
                    route=route,
                ).observe(
                    duration_seconds
                )

            raise

        finally:
            if in_progress_metric is not None:
                in_progress_metric.dec()

            correlation_id_context.reset(
                correlation_token
            )


def _resolve_route_template(
    *,
    request: Request,
    app: FastAPI,
) -> str:
    """
    Resolve the normalized FastAPI route template for metrics.

    Route templates such as
    ``/api/v1/traces/{tenant_id}/{trace_id}``
    prevent high-cardinality Prometheus labels caused by concrete
    request paths.
    """

    matched_route = request.scope.get("route")

    if matched_route is not None:
        route_path = getattr(
            matched_route,
            "path",
            None,
        )

        if route_path:
            return str(route_path)

    for route in app.routes:
        matches, _ = route.matches(
            request.scope
        )

        if matches is Match.FULL:
            route_path = getattr(
                route,
                "path",
                None,
            )

            if route_path:
                return str(route_path)

    return UNKNOWN_ROUTE
