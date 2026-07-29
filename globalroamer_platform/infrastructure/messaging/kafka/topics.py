"""Kafka topic configuration."""

from __future__ import annotations

from dataclasses import dataclass

from globalroamer_platform.core.config import Settings


@dataclass(frozen=True, slots=True)
class KafkaTopics:
    """Kafka topics used by the event transport."""

    integration_events: str
    dead_letter: str

    def __post_init__(self) -> None:
        if not self.integration_events.strip():
            raise ValueError(
                "integration events topic must not be empty"
            )

        if not self.dead_letter.strip():
            raise ValueError(
                "dead-letter topic must not be empty"
            )

        if self.integration_events == self.dead_letter:
            raise ValueError(
                "integration and dead-letter topics must differ"
            )


def build_kafka_topics(
    settings: Settings,
) -> KafkaTopics:
    """Build Kafka topic names from environment settings."""

    return KafkaTopics(
        integration_events=(
            settings.kafka_integration_events_topic.strip()
        ),
        dead_letter=(
            settings.kafka_dead_letter_topic.strip()
        ),
    )
