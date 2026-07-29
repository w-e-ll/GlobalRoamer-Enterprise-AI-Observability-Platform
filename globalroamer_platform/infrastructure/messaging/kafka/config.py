"""Validated Kafka infrastructure configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from globalroamer_platform.core.config import Settings


class KafkaConfig(BaseModel):
    """Runtime configuration used by Kafka adapters."""

    bootstrap_servers: tuple[str, ...]
    client_id: str

    consumer_group_id: str
    auto_offset_reset: Literal[
        "earliest",
        "latest",
        "none",
    ]

    request_timeout_seconds: float = Field(
        gt=0,
        le=300,
    )

    @field_validator("bootstrap_servers")
    @classmethod
    def validate_bootstrap_servers(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if not value:
            raise ValueError(
                "at least one Kafka bootstrap server is required"
            )

        if any(not server.strip() for server in value):
            raise ValueError(
                "Kafka bootstrap servers must not be empty"
            )

        return value

    @field_validator(
        "client_id",
        "consumer_group_id",
    )
    @classmethod
    def validate_non_empty_string(
        cls,
        value: str,
    ) -> str:
        normalized_value = value.strip()

        if not normalized_value:
            raise ValueError(
                "Kafka identifier must not be empty"
            )

        return normalized_value


def build_kafka_config(
    settings: Settings,
) -> KafkaConfig:
    """Build Kafka adapter configuration from environment settings."""

    bootstrap_servers = tuple(
        server.strip()
        for server in settings.kafka_bootstrap_servers.split(",")
        if server.strip()
    )

    return KafkaConfig(
        bootstrap_servers=bootstrap_servers,
        client_id=settings.kafka_client_id,
        consumer_group_id=settings.kafka_consumer_group_id,
        auto_offset_reset=settings.kafka_auto_offset_reset,
        request_timeout_seconds=(
            settings.kafka_request_timeout_seconds
        ),
    )
