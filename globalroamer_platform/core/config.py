# globalroamer_platform/core/config.py

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from globalroamer_platform.core.exceptions import ConfigurationError


class PathSettings(BaseModel):
    base_dir: Path

    input_trace_dir: Path
    input_result_dir: Path
    input_report_dir: Path
    input_template_dir: Path
    input_campaign_dir: Path

    normalized_dir: Path
    chunks_dir: Path
    embeddings_dir: Path
    vector_db_dir: Path

    ai_summary_dir: Path
    root_cause_dir: Path
    campaign_health_dir: Path
    log_dir: Path


class AISettings(BaseModel):
    embedding_model: str
    llm_model: str
    chunk_size: int = Field(ge=100)
    chunk_overlap: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_chunking(self) -> "AISettings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                "chunk_overlap must be smaller than chunk_size"
            )

        return self


class VectorDatabaseSettings(BaseModel):
    provider: str
    collection_name: str
    persist_directory: Path


class ProcessingSettings(BaseModel):
    supported_trace_extensions: list[str]
    supported_result_extensions: list[str]

    save_normalized_json: bool = True
    save_chunks: bool = True

    max_trace_file_size_mb: int = Field(gt=0)
    max_chunk_count_per_trace: int = Field(gt=0)


class LoggingSettings(BaseModel):
    level: str = "INFO"
    format: Literal["text", "json"] = "text"
    rotation_mb: int = Field(default=20, gt=0)
    backup_count: int = Field(default=10, ge=0)


class HealthSettings(BaseModel):
    enabled: bool = True

    database_check_enabled: bool = True
    database_timeout_seconds: float = Field(
        default=3.0,
        gt=0,
        le=30,
    )

    include_environment: bool = True


class MetricsSettings(BaseModel):
    enabled: bool = True

    endpoint_path: str = "/metrics"
    include_in_schema: bool = False

    namespace: str = "globalroamer"
    subsystem: str = "platform"

    @model_validator(mode="after")
    def validate_metrics_settings(self) -> "MetricsSettings":
        if not self.endpoint_path.startswith("/"):
            raise ValueError(
                "metrics endpoint_path must start with '/'"
            )

        if self.endpoint_path == "/":
            raise ValueError(
                "metrics endpoint_path must not be '/'"
            )

        if not self.namespace.strip():
            raise ValueError(
                "metrics namespace must not be empty"
            )

        if not self.subsystem.strip():
            raise ValueError(
                "metrics subsystem must not be empty"
            )

        return self


class TelemetrySettings(BaseModel):
    enabled: bool = False

    service_name: str = "globalroamer-platform"
    service_version: str = "0.1.0"

    otlp_endpoint: str | None = None
    trace_sample_ratio: float = Field(
        default=1.0,
        ge=0,
        le=1,
    )

    instrument_fastapi: bool = True
    instrument_sqlalchemy: bool = True
    instrument_httpx: bool = True

    @model_validator(mode="after")
    def validate_telemetry_settings(
        self,
    ) -> "TelemetrySettings":
        if not self.service_name.strip():
            raise ValueError(
                "telemetry service_name must not be empty"
            )

        if not self.service_version.strip():
            raise ValueError(
                "telemetry service_version must not be empty"
            )

        if (
            self.otlp_endpoint is not None
            and not self.otlp_endpoint.strip()
        ):
            raise ValueError(
                "telemetry otlp_endpoint must be null "
                "or a non-empty value"
            )

        return self


class CampaignHealthSettings(BaseModel):
    degraded_threshold: float = Field(ge=0, le=1)
    critical_threshold: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_thresholds(
        self,
    ) -> "CampaignHealthSettings":
        if self.critical_threshold >= self.degraded_threshold:
            raise ValueError(
                "critical_threshold must be lower than "
                "degraded_threshold"
            )

        return self


class RetryIntelligenceSettings(BaseModel):
    min_historical_matches: int = Field(ge=1)
    low_retry_success_threshold: float = Field(ge=0, le=1)
    cooldown_minutes: int = Field(ge=0)


class PlatformConfig(BaseModel):
    env: str

    paths: PathSettings
    ai: AISettings
    vector_db: VectorDatabaseSettings
    processing: ProcessingSettings
    logging: LoggingSettings

    health: HealthSettings = Field(
        default_factory=HealthSettings,
    )
    metrics: MetricsSettings = Field(
        default_factory=MetricsSettings,
    )
    telemetry: TelemetrySettings = Field(
        default_factory=TelemetrySettings,
    )

    campaign_health: CampaignHealthSettings
    retry_intelligence: RetryIntelligenceSettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = (
        "GlobalRoamer Enterprise AI Observability Platform"
    )
    app_env: str = "local"

    database_url: str
    alembic_database_url: str

    config_file: Path = Path(
        "etc/globalroamer_ai_config.yml"
    )


def _expand_path(
    value: str,
    base_dir: Path,
) -> Path:
    expanded = value.replace(
        "${base_dir}",
        str(base_dir),
    )

    return Path(expanded).expanduser().resolve()


def load_platform_config(
    config_file: Path,
) -> PlatformConfig:
    if not config_file.is_file():
        raise ConfigurationError(
            f"Configuration file was not found: {config_file}"
        )

    try:
        with config_file.open(
            "r",
            encoding="utf-8",
        ) as file:
            raw_config = yaml.safe_load(file)

    except yaml.YAMLError as exc:
        raise ConfigurationError(
            f"Invalid YAML configuration: {config_file}"
        ) from exc

    except OSError as exc:
        raise ConfigurationError(
            f"Cannot read configuration file: {config_file}"
        ) from exc

    if not isinstance(raw_config, dict):
        raise ConfigurationError(
            "Platform configuration must contain "
            "a YAML mapping"
        )

    try:
        paths = raw_config["paths"]
        base_dir = (
            Path(paths["base_dir"])
            .expanduser()
            .resolve()
        )

        resolved_paths = {
            name: (
                base_dir
                if name == "base_dir"
                else _expand_path(
                    value,
                    base_dir,
                )
            )
            for name, value in paths.items()
        }

        raw_config["paths"] = resolved_paths

        persist_directory = raw_config["vector_db"][
            "persist_directory"
        ]

        raw_config["vector_db"]["persist_directory"] = (
            _expand_path(
                persist_directory,
                base_dir,
            )
        )

        return PlatformConfig.model_validate(
            raw_config
        )

    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"Invalid platform configuration: {exc}"
        ) from exc


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_platform_config() -> PlatformConfig:
    settings = get_settings()

    return load_platform_config(
        settings.config_file
    )
