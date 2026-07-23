# globalroamer_platform/main.py

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

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
from globalroamer_platform.bootstrap.chunk_worker import (
    build_chunk_handler_factory,
)
from globalroamer_platform.bootstrap.embedding import (
    build_embedding_handler_factory,
)
from globalroamer_platform.bootstrap.embedding_provider import (
    build_embedding_provider,
)
from globalroamer_platform.bootstrap.event_dispatcher import (
    build_event_dispatcher,
    build_parser_handler_factory,
)
from globalroamer_platform.bootstrap.normalizer_worker import (
    build_normalizer_handler_factory,
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
from globalroamer_platform.runtime.event_runtime import (
    EventRuntime,
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
from globalroamer_platform.api.routes.trace_submission import (
    router as trace_submission_router,
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


embedding_provider = build_embedding_provider(
    model_name=platform_config.ai.embedding_model,
)

parser_handler_factory = build_parser_handler_factory(
    trace_directory=platform_config.paths.input_trace_dir,
    mapping_configuration_path=Path(
        settings.trace_mapping_configuration_path,
    ),
    supported_extensions=(
        platform_config.processing.supported_trace_extensions
    ),
    max_file_size_mb=(
        platform_config.processing.max_trace_file_size_mb
    ),
)

normalizer_handler_factory = (
    build_normalizer_handler_factory()
)

chunk_handler_factory = build_chunk_handler_factory()

embedding_handler_factory = (
    build_embedding_handler_factory(
        embedding_provider=embedding_provider,
    )
)

event_dispatcher = build_event_dispatcher(
    session_factory=async_session_factory,
    parser_handler_factory=parser_handler_factory,
    normalizer_handler_factory=normalizer_handler_factory,
    chunk_handler_factory=chunk_handler_factory,
    embedding_handler_factory=embedding_handler_factory,
)

event_runtime = EventRuntime(
    dispatcher=event_dispatcher,
)

application_runtime = build_application_runtime(
    session_factory=async_session_factory,
    event_runtime=event_runtime,
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

app.include_router(
    trace_submission_router,
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
