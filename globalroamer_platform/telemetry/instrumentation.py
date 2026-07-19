# globalroamer_platform/telemetry/instrumentation.py

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import (
    FastAPIInstrumentor,
)
from opentelemetry.instrumentation.httpx import (
    HTTPXClientInstrumentor,
)
from opentelemetry.instrumentation.sqlalchemy import (
    SQLAlchemyInstrumentor,
)
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.ext.asyncio import AsyncEngine

from globalroamer_platform.core.config import (
    TelemetrySettings,
)
from globalroamer_platform.telemetry.tracing import (
    TracingState,
)


@dataclass(frozen=True, slots=True)
class InstrumentationState:
    """Track instrumentation enabled for the application."""

    app: FastAPI
    fastapi_enabled: bool
    sqlalchemy_enabled: bool
    httpx_enabled: bool


_instrumentation_state: InstrumentationState | None = None


def configure_instrumentation(
    *,
    app: FastAPI,
    engine: AsyncEngine,
    settings: TelemetrySettings,
    tracing_state: TracingState | None,
) -> InstrumentationState | None:
    """
    Configure supported OpenTelemetry instrumentations.

    Instrumentation is not installed when telemetry is disabled.
    Calling this function repeatedly for the same application returns
    the existing state instead of instrumenting libraries twice.
    """

    global _instrumentation_state

    if not settings.enabled:
        return None

    if tracing_state is None:
        raise RuntimeError(
            "OpenTelemetry tracing must be configured before "
            "application instrumentation"
        )

    if _instrumentation_state is not None:
        if _instrumentation_state.app is not app:
            raise RuntimeError(
                "OpenTelemetry instrumentation was already "
                "configured for another FastAPI application"
            )

        return _instrumentation_state

    tracer_provider = tracing_state.provider

    fastapi_enabled = False
    sqlalchemy_enabled = False
    httpx_enabled = False

    try:
        if settings.instrument_fastapi:
            _instrument_fastapi(
                app=app,
                tracer_provider=tracer_provider,
            )
            fastapi_enabled = True

        if settings.instrument_sqlalchemy:
            _instrument_sqlalchemy(
                engine=engine,
                tracer_provider=tracer_provider,
            )
            sqlalchemy_enabled = True

        if settings.instrument_httpx:
            _instrument_httpx(
                tracer_provider=tracer_provider,
            )
            httpx_enabled = True

    except Exception:
        _rollback_instrumentation(
            app=app,
            fastapi_enabled=fastapi_enabled,
            sqlalchemy_enabled=sqlalchemy_enabled,
            httpx_enabled=httpx_enabled,
        )
        raise

    _instrumentation_state = InstrumentationState(
        app=app,
        fastapi_enabled=fastapi_enabled,
        sqlalchemy_enabled=sqlalchemy_enabled,
        httpx_enabled=httpx_enabled,
    )

    return _instrumentation_state


def _instrument_fastapi(
    *,
    app: FastAPI,
    tracer_provider: TracerProvider,
) -> None:
    """
    Instrument incoming FastAPI requests.

    FastAPI instrumentation creates server spans and propagates
    distributed tracing context through incoming HTTP requests.
    """

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
    )


def _instrument_sqlalchemy(
    *,
    engine: AsyncEngine,
    tracer_provider: TracerProvider,
) -> None:
    """
    Instrument SQLAlchemy database operations.

    SQLAlchemy instrumentation operates on the synchronous engine
    wrapped by SQLAlchemy's AsyncEngine.
    """

    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine,
        tracer_provider=tracer_provider,
    )


def _instrument_httpx(
    *,
    tracer_provider: TracerProvider,
) -> None:
    """
    Instrument outgoing synchronous and asynchronous HTTPX requests.
    """

    HTTPXClientInstrumentor().instrument(
        tracer_provider=tracer_provider,
    )


def shutdown_instrumentation() -> None:
    """
    Remove installed OpenTelemetry instrumentations.

    This should run during application shutdown before the tracing
    provider itself is shut down.
    """

    global _instrumentation_state

    state = _instrumentation_state

    if state is None:
        return

    if state.httpx_enabled:
        HTTPXClientInstrumentor().uninstrument()

    if state.sqlalchemy_enabled:
        SQLAlchemyInstrumentor().uninstrument()

    if state.fastapi_enabled:
        FastAPIInstrumentor.uninstrument_app(
            state.app
        )

    _instrumentation_state = None


def get_instrumentation_state() -> InstrumentationState | None:
    """Return the current instrumentation state."""

    return _instrumentation_state


def _rollback_instrumentation(
    *,
    app: FastAPI,
    fastapi_enabled: bool,
    sqlalchemy_enabled: bool,
    httpx_enabled: bool,
) -> None:
    """
    Undo partially configured instrumentation after startup failure.
    """

    if httpx_enabled:
        HTTPXClientInstrumentor().uninstrument()

    if sqlalchemy_enabled:
        SQLAlchemyInstrumentor().uninstrument()

    if fastapi_enabled:
        FastAPIInstrumentor.uninstrument_app(
            app
        )


def reset_instrumentation_for_testing() -> None:
    """
    Reset instrumentation state for isolated automated tests.
    """

    shutdown_instrumentation()
