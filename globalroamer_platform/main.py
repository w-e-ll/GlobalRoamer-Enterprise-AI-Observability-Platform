# globalroamer_platform/main.py

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from globalroamer_platform.api.middleware.request_logging import (
    register_request_logging,
)
from globalroamer_platform.api.routes.health import (
    router as health_router,
)
from globalroamer_platform.api.routes.trace_processing import (
    router as trace_processing_router,
)
from globalroamer_platform.api.routes.traces import (
    router as traces_router,
)
from globalroamer_platform.bootstrap.runtime import (
    build_application_runtime,
)
from globalroamer_platform.core.config import (
    get_platform_config,
    get_settings,
)
from globalroamer_platform.core.logging import setup_logging
from globalroamer_platform.core.startup import (
    validate_startup_configuration,
)
from globalroamer_platform.infrastructure.database.session import (
    async_session_factory,
    engine,
)
from globalroamer_platform.infrastructure.messaging.in_memory_event_publisher import (
    InMemoryEventPublisher,
)
from globalroamer_platform.telemetry.instrumentation import (
    configure_instrumentation,
    shutdown_instrumentation,
)
from globalroamer_platform.telemetry.metrics import (
    configure_metrics,
    register_metrics_endpoint,
)
from globalroamer_platform.telemetry.tracing import (
    configure_tracing,
    shutdown_tracing,
)


settings = get_settings()
platform_config = get_platform_config()


setup_logging(
    settings=platform_config.logging,
    log_file=platform_config.paths.log_dir / "api.log",
    stdout=True,
)


configure_metrics(
    settings=platform_config.metrics,
    app_name=settings.app_name,
    environment=settings.app_env,
    version=platform_config.telemetry.service_version,
)


tracing_state = configure_tracing(
    settings=platform_config.telemetry,
    environment=settings.app_env,
)


event_publisher = InMemoryEventPublisher()

application_runtime = build_application_runtime(
    session_factory=async_session_factory,
    event_publisher=event_publisher,
)


@asynccontextmanager
async def lifespan(
    _app: FastAPI,
) -> AsyncIterator[None]:
    """
    Manage application startup and shutdown.

    Startup validates operational configuration and starts managed
    background workers before accepting traffic. Shutdown stops workers
    gracefully, releases database resources, and flushes telemetry.
    """
    validate_startup_configuration(
        settings=settings,
        platform_config=platform_config,
    )

    await application_runtime.start()

    try:
        yield
    finally:
        await application_runtime.stop()
        shutdown_instrumentation()
        shutdown_tracing()
        await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=platform_config.telemetry.service_version,
    lifespan=lifespan,
)


register_request_logging(app)


app.include_router(
    health_router,
)

app.include_router(
    traces_router,
    prefix="/api/v1",
)

app.include_router(
    trace_processing_router,
)


register_metrics_endpoint(
    app=app,
    settings=platform_config.metrics,
)


configure_instrumentation(
    app=app,
    engine=engine,
    settings=platform_config.telemetry,
    tracing_state=tracing_state,
)
