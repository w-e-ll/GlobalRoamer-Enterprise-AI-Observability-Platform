"""Tests for Kafka topic configuration."""

from __future__ import annotations

import pytest

from globalroamer_platform.core.config import Settings
from globalroamer_platform.infrastructure.messaging.kafka.topics import (
    KafkaTopics,
    build_kafka_topics,
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


def test_build_kafka_topics_uses_defaults() -> None:
    topics = build_kafka_topics(
        build_settings()
    )

    assert (
        topics.integration_events
        == "globalroamer.integration-events.v1"
    )
    assert (
        topics.dead_letter
        == "globalroamer.integration-events.dlq.v1"
    )


def test_kafka_topics_reject_empty_integration_topic() -> None:
    with pytest.raises(
        ValueError,
        match="integration events topic must not be empty",
    ):
        KafkaTopics(
            integration_events=" ",
            dead_letter="events.dlq",
        )


def test_kafka_topics_reject_same_topic_names() -> None:
    with pytest.raises(
        ValueError,
        match="topics must differ",
    ):
        KafkaTopics(
            integration_events="events",
            dead_letter="events",
        )
