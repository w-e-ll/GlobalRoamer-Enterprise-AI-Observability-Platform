# globalroamer_platform/api/routes/health.py

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from globalroamer_platform.core.config import get_settings
from globalroamer_platform.infrastructure.database.health import (
    check_database_health,
)


router = APIRouter(
    tags=["health"],
)

settings = get_settings()


@router.get(
    "/live",
    summary="Liveness check",
    status_code=status.HTTP_200_OK,
)
async def liveness() -> dict[str, str]:
    """
    Confirm that the API process is running.

    This endpoint must not depend on PostgreSQL or any external service.
    """

    return {
        "status": "alive",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@router.get(
    "/ready",
    summary="Readiness check",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Application is not ready",
        },
    },
)
async def readiness() -> JSONResponse:
    """
    Confirm that the application is ready to receive traffic.

    The application is considered ready only when required
    infrastructure dependencies are available.
    """

    database_healthy = await check_database_health()

    if not database_healthy:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "service": settings.app_name,
                "environment": settings.app_env,
                "components": {
                    "database": "unhealthy",
                },
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "ready",
            "service": settings.app_name,
            "environment": settings.app_env,
            "components": {
                "database": "healthy",
            },
        },
    )


@router.get(
    "/health",
    summary="Application health check",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Application is unhealthy",
        },
    },
)
async def health() -> JSONResponse:
    """
    Return the aggregated health status of the application.

    Additional components such as the vector database, workers,
    filesystem and external AI providers can be added later.
    """

    database_healthy = await check_database_health()

    application_status = (
        "healthy"
        if database_healthy
        else "unhealthy"
    )

    status_code = (
        status.HTTP_200_OK
        if database_healthy
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    return JSONResponse(
        status_code=status_code,
        content={
            "status": application_status,
            "service": settings.app_name,
            "environment": settings.app_env,
            "components": {
                "api": "healthy",
                "database": (
                    "healthy"
                    if database_healthy
                    else "unhealthy"
                ),
            },
        },
    )
