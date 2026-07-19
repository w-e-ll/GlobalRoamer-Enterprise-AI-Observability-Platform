# globalroamer_platform/main.py

from fastapi import FastAPI

from globalroamer_platform.core.config import get_settings


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)


@app.get("/health", tags=["platform"])
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.app_env,
    }
