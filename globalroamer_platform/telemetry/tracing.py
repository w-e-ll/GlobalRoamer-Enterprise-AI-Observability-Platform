# globalroamer_platform/telemetry/tracing.py

from __future__ import annotations

from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import (
    DEPLOYMENT_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
)
from opentelemetry.sdk.trace.sampling import (
    ParentBased,
    TraceIdRatioBased,
)
from opentelemetry.trace import Tracer

from globalroamer_platform.core.config import (
    TelemetrySettings,
)


@dataclass(frozen=True, slots=True)
class TracingState:
    """Configured OpenTelemetry tracing components."""

    provider: TracerProvider
    tracer: Tracer


_tracing_state: TracingState | None = None
_tracing_settings: TelemetrySettings | None = None


def configure_tracing(
    settings: TelemetrySettings,
    *,
    environment: str,
) -> TracingState | None:
    """
    Configure OpenTelemetry distributed tracing.

    Returns None when telemetry is disabled.

    Repeated calls with the same settings return the existing
    tracing state. Reconfiguration with different settings is
    rejected because OpenTelemetry supports one global provider.
    """

    global _tracing_state
    global _tracing_settings

    if not settings.enabled:
        return None

    if _tracing_state is not None:
        if _tracing_settings != settings:
            raise RuntimeError(
                "OpenTelemetry tracing was already configured "
                "with different settings"
            )

        return _tracing_state

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "deployment.environment.name": environment,
        }
    )

    sampler = ParentBased(
        root=TraceIdRatioBased(
            settings.trace_sample_ratio
        )
    )

    provider = TracerProvider(
        resource=resource,
        sampler=sampler,
    )

    if settings.otlp_endpoint is not None:
        exporter = OTLPSpanExporter(
            endpoint=settings.otlp_endpoint,
            insecure=_is_insecure_endpoint(
                settings.otlp_endpoint
            ),
        )

        provider.add_span_processor(
            BatchSpanProcessor(exporter)
        )

    trace.set_tracer_provider(provider)

    tracer = trace.get_tracer(
        instrumenting_module_name=(
            "globalroamer_platform"
        ),
        instrumenting_library_version=(
            settings.service_version
        ),
    )

    _tracing_state = TracingState(
        provider=provider,
        tracer=tracer,
    )
    _tracing_settings = settings

    return _tracing_state


def get_tracer(
    name: str = "globalroamer_platform",
    *,
    version: str | None = None,
) -> Tracer:
    """
    Return an OpenTelemetry tracer.

    When telemetry is disabled, OpenTelemetry returns a no-op tracer,
    so application code does not need telemetry-specific conditions.
    """

    return trace.get_tracer(
        instrumenting_module_name=name,
        instrumenting_library_version=version,
    )


def get_current_trace_id() -> str | None:
    """
    Return the active OpenTelemetry trace ID as a hexadecimal string.

    Returns None when there is no active valid span.
    """

    span = trace.get_current_span()
    span_context = span.get_span_context()

    if not span_context.is_valid:
        return None

    return format(
        span_context.trace_id,
        "032x",
    )


def get_current_span_id() -> str | None:
    """
    Return the active OpenTelemetry span ID as a hexadecimal string.

    Returns None when there is no active valid span.
    """

    span = trace.get_current_span()
    span_context = span.get_span_context()

    if not span_context.is_valid:
        return None

    return format(
        span_context.span_id,
        "016x",
    )


def shutdown_tracing() -> None:
    """
    Flush pending spans and shut down the tracing provider.

    This should be called during application shutdown.
    """

    global _tracing_state
    global _tracing_settings

    if _tracing_state is None:
        return

    _tracing_state.provider.shutdown()

    _tracing_state = None
    _tracing_settings = None


def force_flush_tracing(
    timeout_millis: int = 30_000,
) -> bool:
    """
    Flush pending spans immediately.

    Primarily useful before controlled process termination and
    in integration tests.
    """

    if _tracing_state is None:
        return True

    return _tracing_state.provider.force_flush(
        timeout_millis=timeout_millis
    )


def _is_insecure_endpoint(
    endpoint: str,
) -> bool:
    """
    Determine whether the OTLP gRPC exporter should use plaintext.

    Local collectors commonly expose an http:// endpoint, while
    production collectors generally use TLS through https://.
    """

    return endpoint.strip().lower().startswith(
        "http://"
    )


def reset_tracing_for_testing() -> None:
    """
    Reset local tracing state for isolated tests.

    OpenTelemetry's global provider cannot reliably be replaced after
    initialization, so production code must use shutdown_tracing()
    rather than this helper.
    """

    global _tracing_state
    global _tracing_settings

    if _tracing_state is not None:
        _tracing_state.provider.shutdown()

    _tracing_state = None
    _tracing_settings = None
