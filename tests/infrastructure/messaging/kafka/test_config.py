"""Tests for Kafka infrastructure configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from globalroamer_platform.core.config import Settings
from globalroamer_platform.infrastructure.messaging.kafka.config import (
    build_kafka_config,
)


def build_settings(
    **overrides: object,
) -> Settings:
    values: dict[str, object] = {
        "database_url": (
            "postgresql+asyncpg://user:password@postgres/db"
        ),
        "alembic_database_url": (
            "postgresql+psycopg://user:password@postgres/db"
        ),
        "_env_file": None,
    }
    values.update(overrides)

    return Settings(**values)


def test_build_kafka_config_uses_defaults() -> None:
    config = build_kafka_config(
        build_settings()
    )

    assert config.bootstrap_servers == ("kafka:9092",)
    assert config.client_id == "globalroamer-platform"
    assert (
        config.consumer_group_id
        == "globalroamer.pipeline-workers.v1"
    )
    assert config.auto_offset_reset == "earliest"
    assert config.request_timeout_seconds == 30.0


def test_build_kafka_config_parses_multiple_servers() -> None:
    config = build_kafka_config(
        build_settings(
            kafka_bootstrap_servers=(
                "kafka-1:9092, kafka-2:9092"
            ),
        )
    )

    assert config.bootstrap_servers == (
        "kafka-1:9092",
        "kafka-2:9092",
    )


def test_build_kafka_config_rejects_empty_servers() -> None:
    with pytest.raises(
        ValidationError,
        match="at least one Kafka bootstrap server",
    ):
        build_kafka_config(
            build_settings(
                kafka_bootstrap_servers=" , ",
            )
        )


def test_settings_reject_invalid_offset_reset() -> None:
    with pytest.raises(ValidationError):
        build_settings(
            kafka_auto_offset_reset="invalid",
        )


def test_settings_reject_non_positive_timeout() -> None:
    with pytest.raises(ValidationError):
        build_settings(
            kafka_request_timeout_seconds=0,
        )
