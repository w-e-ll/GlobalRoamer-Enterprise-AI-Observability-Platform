from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "GlobalRoamer Enterprise AI Observability Platform"
    app_env: str = "local"

    database_url: str
    alembic_database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
