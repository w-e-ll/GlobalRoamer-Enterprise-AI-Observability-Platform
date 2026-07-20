# globalroamer_platform/core/startup.py

import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from globalroamer_platform.core.config import (
    PlatformConfig,
    Settings,
)
from globalroamer_platform.core.exceptions import ConfigurationError

from globalroamer_platform.bootstrap.settings import (
    build_trace_parsing_settings,
)
from globalroamer_platform.bootstrap.trace_parsing import (
    build_trace_parsing_container,
    validate_trace_parsing_configuration,
)


logger = logging.getLogger(__name__)


SUPPORTED_ENVIRONMENTS = {
    "local",
    "development",
    "test",
    "uat",
    "staging",
    "production",
}

SUPPORTED_VECTOR_DATABASE_PROVIDERS = {
    "chromadb",
}

PRODUCTION_ENVIRONMENTS = {
    "production",
}

INSECURE_PASSWORDS = {
    "",
    "change_me",
    "changeme",
    "password",
    "postgres",
}


def build_application_state(settings: Settings):
    trace_parsing_settings = build_trace_parsing_settings(
        settings
    )

    trace_parsing = build_trace_parsing_container(
        settings=trace_parsing_settings
    )

    validate_trace_parsing_configuration(
        trace_parsing
    )

    return trace_parsing


def validate_startup_configuration(
    *,
    settings: Settings,
    platform_config: PlatformConfig,
) -> None:
    """
    Validate configuration assumptions required to start the application.

    Pydantic validates configuration structure and field constraints.
    This function validates operational requirements such as directories,
    environment consistency, providers and database configuration.
    """

    logger.info(
        "Startup configuration validation started "
        "environment=%s",
        settings.app_env,
    )

    app_environment = _normalize_environment(
        settings.app_env,
        source="APP_ENV",
    )
    platform_environment = _normalize_environment(
        platform_config.env,
        source="platform configuration env",
    )

    _validate_environment_consistency(
        app_environment=app_environment,
        platform_environment=platform_environment,
    )

    _validate_database_url(
        database_url=settings.database_url,
        environment=app_environment,
    )

    _validate_processing_configuration(platform_config)
    _validate_ai_configuration(platform_config)
    _validate_vector_database_configuration(platform_config)
    _validate_directories(platform_config)

    logger.info(
        "Startup configuration validation completed "
        "environment=%s vector_provider=%s",
        app_environment,
        platform_config.vector_db.provider,
    )


def _normalize_environment(
    value: str,
    *,
    source: str,
) -> str:
    normalized_value = value.strip().lower()

    if not normalized_value:
        raise ConfigurationError(
            f"{source} must not be empty"
        )

    if normalized_value not in SUPPORTED_ENVIRONMENTS:
        supported_values = ", ".join(
            sorted(SUPPORTED_ENVIRONMENTS)
        )
        raise ConfigurationError(
            f"Unsupported {source}: {value}. "
            f"Supported values: {supported_values}"
        )

    return normalized_value


def _validate_environment_consistency(
    *,
    app_environment: str,
    platform_environment: str,
) -> None:
    if app_environment != platform_environment:
        raise ConfigurationError(
            "Environment configuration mismatch: "
            f"APP_ENV={app_environment}, "
            f"platform env={platform_environment}"
        )


def _validate_database_url(
    *,
    database_url: str,
    environment: str,
) -> None:
    try:
        parsed_url = make_url(database_url)
    except ArgumentError as exc:
        raise ConfigurationError(
            "DATABASE_URL is invalid"
        ) from exc

    if not parsed_url.drivername:
        raise ConfigurationError(
            "DATABASE_URL must define a database driver"
        )

    if not parsed_url.database:
        raise ConfigurationError(
            "DATABASE_URL must define a database name"
        )

    if environment not in PRODUCTION_ENVIRONMENTS:
        return

    password = parsed_url.password or ""

    if password.strip().lower() in INSECURE_PASSWORDS:
        raise ConfigurationError(
            "DATABASE_URL uses an insecure default password "
            f"in the {environment} environment"
        )


def _validate_processing_configuration(
    platform_config: PlatformConfig,
) -> None:
    trace_extensions = (
        platform_config.processing.supported_trace_extensions
    )
    result_extensions = (
        platform_config.processing.supported_result_extensions
    )

    if not trace_extensions:
        raise ConfigurationError(
            "At least one supported trace extension is required"
        )

    if not result_extensions:
        raise ConfigurationError(
            "At least one supported result extension is required"
        )

    _validate_file_extensions(
        trace_extensions,
        setting_name="supported_trace_extensions",
    )
    _validate_file_extensions(
        result_extensions,
        setting_name="supported_result_extensions",
    )


def _validate_file_extensions(
    extensions: list[str],
    *,
    setting_name: str,
) -> None:
    normalized_extensions: set[str] = set()

    for extension in extensions:
        normalized_extension = extension.strip().lower()

        if not normalized_extension.startswith("."):
            raise ConfigurationError(
                f"{setting_name} contains an invalid extension: "
                f"{extension}. Extensions must start with '.'"
            )

        if normalized_extension in normalized_extensions:
            raise ConfigurationError(
                f"{setting_name} contains a duplicate extension: "
                f"{extension}"
            )

        normalized_extensions.add(normalized_extension)


def _validate_ai_configuration(
    platform_config: PlatformConfig,
) -> None:
    if not platform_config.ai.embedding_model.strip():
        raise ConfigurationError(
            "AI embedding model must not be empty"
        )

    if not platform_config.ai.llm_model.strip():
        raise ConfigurationError(
            "AI LLM model must not be empty"
        )


def _validate_vector_database_configuration(
    platform_config: PlatformConfig,
) -> None:
    provider = (
        platform_config.vector_db.provider
        .strip()
        .lower()
    )

    if provider not in SUPPORTED_VECTOR_DATABASE_PROVIDERS:
        supported_providers = ", ".join(
            sorted(SUPPORTED_VECTOR_DATABASE_PROVIDERS)
        )
        raise ConfigurationError(
            f"Unsupported vector database provider: {provider}. "
            f"Supported providers: {supported_providers}"
        )

    if not platform_config.vector_db.collection_name.strip():
        raise ConfigurationError(
            "Vector database collection name must not be empty"
        )


def _validate_directories(
    platform_config: PlatformConfig,
) -> None:
    paths = platform_config.paths

    directories = {
        "base_dir": paths.base_dir,
        "input_trace_dir": paths.input_trace_dir,
        "input_result_dir": paths.input_result_dir,
        "input_report_dir": paths.input_report_dir,
        "input_template_dir": paths.input_template_dir,
        "input_campaign_dir": paths.input_campaign_dir,
        "normalized_dir": paths.normalized_dir,
        "chunks_dir": paths.chunks_dir,
        "embeddings_dir": paths.embeddings_dir,
        "vector_db_dir": paths.vector_db_dir,
        "ai_summary_dir": paths.ai_summary_dir,
        "root_cause_dir": paths.root_cause_dir,
        "campaign_health_dir": paths.campaign_health_dir,
        "log_dir": paths.log_dir,
        "vector_db_persist_directory": (
            platform_config.vector_db.persist_directory
        ),
    }

    for name, directory in directories.items():
        _ensure_directory(
            name=name,
            directory=directory,
        )


def _ensure_directory(
    *,
    name: str,
    directory: Path,
) -> None:
    try:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )
    except OSError as exc:
        raise ConfigurationError(
            f"Cannot create configured directory "
            f"{name}: {directory}"
        ) from exc

    if not directory.is_dir():
        raise ConfigurationError(
            f"Configured path is not a directory "
            f"{name}: {directory}"
        )

    if not os.access(directory, os.R_OK):
        raise ConfigurationError(
            f"Configured directory is not readable "
            f"{name}: {directory}"
        )

    _verify_directory_is_writable(
        name=name,
        directory=directory,
    )


def _verify_directory_is_writable(
    *,
    name: str,
    directory: Path,
) -> None:
    try:
        with NamedTemporaryFile(
            mode="w",
            prefix=".startup-check-",
            dir=directory,
            delete=True,
            encoding="utf-8",
        ) as temporary_file:
            temporary_file.write("startup-check")
            temporary_file.flush()

    except OSError as exc:
        raise ConfigurationError(
            f"Configured directory is not writable "
            f"{name}: {directory}"
        ) from exc
