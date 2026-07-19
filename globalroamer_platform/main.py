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
from globalroamer_platform.api.routes.traces import (
    router as traces_router,
)
from globalroamer_platform.core.config import (
    get_platform_config,
    get_settings,
)
from globalroamer_platform.core.logging import setup_logging
from globalroamer_platform.core.startup import (
    validate_startup_configuration,
)


settings = get_settings()
platform_config = get_platform_config()


setup_logging(
    settings=platform_config.logging,
    log_file=platform_config.paths.log_dir / "api.log",
    stdout=True,
)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    """
    Manage application startup and shutdown.

    Startup validation runs before the application begins
    accepting HTTP traffic.
    """

    validate_startup_configuration(
        settings=settings,
        platform_config=platform_config,
    )

    yield


app = FastAPI(
    title=settings.app_name,
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
