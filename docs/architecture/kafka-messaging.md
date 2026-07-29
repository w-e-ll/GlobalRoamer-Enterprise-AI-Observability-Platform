# Kafka Messaging Architecture

## Status

Accepted for implementation.

## Context

GlobalRoamer currently uses a transactional outbox combined with an in-process event runtime.

The current event flow is:

    Business transaction
            |
            v
    Transactional outbox
            |
            v
    OutboxWorker
            |
            v
    PublishPendingOutboxMessages
            |
            v
    EventRuntime
            |
            v
    asyncio.Queue
            |
            v
    EventDispatcher
            |
            v
    Application event handlers

The current implementation is useful for deterministic tests and local development, but it does not provide durable cross-process event delivery.

The platform requires a production-capable event transport before adding retrieval, RAG, AI summaries, root-cause analysis, and retry intelligence.

## Decision

Kafka will become the production integration-event transport.

The target event flow is:

    Business transaction
            |
            v
    Transactional outbox
            |
            v
    OutboxWorker
            |
            v
    KafkaEventPublisher
            |
            v
    Kafka topic
            |
            v
    KafkaConsumerRuntime
            |
            v
    EventDispatcher
            |
            v
    Application event handlers

Kafka is introduced as an infrastructure adapter.

The application and domain layers must not import Kafka-specific classes.

## Goals

The Kafka integration must provide:

- durable event publication;
- cross-process event delivery;
- consumer groups;
- ordered processing within a partition;
- explicit offset management;
- graceful startup and shutdown;
- retry and dead-letter support;
- transport-independent application handlers;
- testable serialization and runtime behavior.

## Non-goals

This change does not introduce microservices.

The API, outbox publisher, Kafka consumer, dispatcher, and handlers may initially run as separate processes while remaining part of the same deployable codebase.

This change does not modify business workflows.

## Existing contracts retained

The following contracts remain unchanged:

- `EventEnvelope`
- `EventPublisher`
- `EventDispatcher`
- `EventHandler`
- `PublishPendingOutboxMessages`
- `OutboxRepository`
- `OutboxWorker`

`KafkaEventPublisher` will implement the existing `EventPublisher` port.

`KafkaConsumerRuntime` will consume records and invoke the existing `EventDispatcher`.

## Components

### KafkaEventPublisher

Responsibilities:

- serialize an `EventEnvelope`;
- select the configured topic;
- derive the Kafka message key;
- publish the event;
- wait for broker acknowledgement;
- propagate publication failures to the outbox service.

It must not:

- update outbox state;
- dispatch events locally;
- perform business retries;
- invoke application handlers.

### KafkaConsumerRuntime

Responsibilities:

- subscribe to the integration-events topic;
- receive Kafka records;
- deserialize records into `EventEnvelope` objects;
- dispatch events through `EventDispatcher`;
- publish follow-up events through `EventPublisher`;
- commit offsets only after successful processing;
- stop gracefully.

It must not:

- contain business logic;
- instantiate handlers directly;
- modify domain entities directly;
- silently discard unsupported or malformed messages.

### EventDispatcher

The dispatcher remains transport-independent.

It routes events by `event_type` to registered application handlers.

### Transactional outbox

The outbox remains the source of durable publication intent.

An outbox message is marked as published only after the Kafka producer confirms successful broker delivery.

## Topic strategy

Initial topic:

    globalroamer.integration-events.v1

Initial dead-letter topic:

    globalroamer.integration-events.dlq.v1

A single integration-events topic is sufficient for the current platform.

Topic separation may be introduced later when required by:

- different retention policies;
- different throughput profiles;
- security boundaries;
- independently scaling consumers;
- operational isolation.

## Consumer group

Initial consumer group:

    globalroamer.pipeline-workers.v1

Consumers in this group cooperatively process integration events.

## Partition key

The initial Kafka message key is:

    correlation_id

All events belonging to the same processing chain should share the same correlation identifier.

Using `correlation_id` as the key preserves ordering for the complete trace processing workflow within a Kafka partition.

The key must not be `event_id`, because every event has a unique identifier and related workflow events could then be assigned to different partitions.

## Event contract

Kafka values contain the serialized `EventEnvelope`.

Example:

    {
      "event_id": "40cc11a7-c216-461d-bdef-6426110182a5",
      "event_type": "trace.artifact.received",
      "event_version": 1,
      "correlation_id": "trace-2026-07-29-001",
      "causation_id": null,
      "tenant_id": "default",
      "occurred_at": "2026-07-29T12:00:00Z",
      "producer": "globalroamer-api",
      "payload": {
        "artifact_id": "08c872a0-6929-4759-a693-7ae48e177546"
      }
    }

Serialization format:

    UTF-8 JSON

Required rules:

- UUID values are serialized as strings;
- timestamps are serialized as ISO 8601;
- timestamps must include timezone information;
- payload must be a JSON object;
- unknown event types remain valid envelopes;
- invalid envelopes must not reach application handlers.

## Headers

Initial Kafka headers:

- `event_id`
- `event_type`
- `event_version`
- `correlation_id`
- `tenant_id`
- `producer`
- `content_type`

The serialized envelope remains the authoritative event representation.

Headers exist for diagnostics, filtering, and broker tooling.

## Delivery semantics

The platform uses at-least-once delivery.

Exactly-once end-to-end processing is not assumed.

Reasons:

- Kafka acknowledgements and database transactions are separate boundaries;
- a consumer may finish database work before its offset is committed;
- a consumer may therefore receive the same event more than once.

Application handlers must eventually become idempotent.

## Producer acknowledgement policy

The producer must wait for Kafka acknowledgement before returning from `publish()`.

The outbox message is marked as published only after the producer call succeeds.

Recommended producer behavior:

    acks=all
    enable_idempotence=true

Kafka library-specific configuration will be isolated inside the infrastructure adapter.

## Consumer offset policy

Automatic offset commits are disabled.

The consumer commits an offset only after:

1. the Kafka record is deserialized;
2. the event is successfully dispatched;
3. all handler database transactions commit;
4. follow-up event publication succeeds.

When processing fails, the offset must not be committed.

## Follow-up events

Handlers currently return follow-up `EventEnvelope` objects.

The Kafka consumer runtime must publish those events through an injected `EventPublisher`.

Follow-up events must not be inserted into an in-memory queue.

Target flow:

    Kafka record
        |
        v
    EventDispatcher
        |
        v
    Follow-up EventEnvelope
        |
        v
    KafkaEventPublisher
        |
        v
    Kafka topic

A later improvement may persist follow-up events through a transactional outbox inside each handler transaction.

That improvement is intentionally outside the first Kafka milestone.

## Error handling

### Producer errors

Producer exceptions propagate to `PublishPendingOutboxMessages`.

The existing outbox retry policy remains responsible for:

- retry scheduling;
- exponential backoff;
- maximum attempts;
- permanent failure state.

### Deserialization errors

Malformed messages must not be passed to `EventDispatcher`.

Initial behavior:

- log the failure;
- include topic, partition, offset, and available headers;
- publish the original record and failure metadata to the DLQ;
- commit the original offset after successful DLQ publication.

### Handler errors

Initial behavior:

- log the error;
- do not commit the offset;
- allow Kafka redelivery.

A bounded retry policy and DLQ routing will be implemented in a later reliability milestone.

## Idempotency

At-least-once delivery requires idempotent consumers.

The first Kafka milestone will preserve current behavior.

A later milestone will introduce a durable inbox or processed-event table keyed by:

    event_id
    consumer_name

Before handling an event, the consumer will verify whether that event has already been processed by that consumer.

## Runtime lifecycle

Producer lifecycle:

    create
    start
    publish repeatedly
    flush
    stop

Consumer lifecycle:

    create
    start
    subscribe
    poll
    dispatch
    commit
    stop

Producer and consumer clients are long-lived.

They must not be recreated for each event or each polling iteration.

## Package structure

Initial structure:

    globalroamer_platform/
        infrastructure/
            messaging/
                kafka/
                    __init__.py
                    config.py
                    topics.py
                    serializer.py
                    producer.py
                    consumer.py

        runtime/
            kafka_consumer_runtime.py

        bootstrap/
            kafka.py
            runtime.py

Tests:

    tests/
        infrastructure/
            messaging/
                kafka/
                    test_config.py
                    test_topics.py
                    test_serializer.py
                    test_producer.py
                    test_consumer.py

        runtime/
            test_kafka_consumer_runtime.py

## Configuration

Environment variables:

    KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    KAFKA_CLIENT_ID=globalroamer-platform
    KAFKA_INTEGRATION_EVENTS_TOPIC=globalroamer.integration-events.v1
    KAFKA_DEAD_LETTER_TOPIC=globalroamer.integration-events.dlq.v1
    KAFKA_CONSUMER_GROUP_ID=globalroamer.pipeline-workers.v1
    KAFKA_AUTO_OFFSET_RESET=earliest
    KAFKA_REQUEST_TIMEOUT_SECONDS=30

Configuration must be represented by validated Pydantic settings.

Kafka-specific configuration must not be added to the YAML platform configuration.

Operational connection settings belong to environment-based `Settings`.

## Local infrastructure

Docker Compose will run Kafka in KRaft mode.

Initial services:

- postgres
- migration
- kafka
- kafka-ui
- api

The initial local environment uses a single Kafka broker.

This is suitable for development and demonstrations, but not intended to represent a highly available production Kafka cluster.

## Migration plan

### Milestone 1: infrastructure and configuration

Add:

- Kafka KRaft service;
- Kafka UI;
- environment settings;
- topic constants;
- configuration validation;
- configuration tests.

No event flow changes.

### Milestone 2: serialization

Add:

- `EventEnvelope` serializer;
- `EventEnvelope` deserializer;
- round-trip tests;
- invalid-message tests.

No broker connection required for unit tests.

### Milestone 3: producer

Add:

- Kafka client dependency;
- `KafkaEventPublisher`;
- producer lifecycle;
- mocked producer tests;
- optional broker integration test.

The outbox will publish to Kafka.

### Milestone 4: consumer

Add:

- `KafkaConsumerRuntime`;
- explicit offset commits;
- `EventDispatcher` integration;
- follow-up event publication;
- graceful shutdown;
- consumer runtime tests.

### Milestone 5: process separation

Run:

- API process
- outbox publisher process
- Kafka consumer process

Remove production dependency on `EventRuntime`.

Retain `EventRuntime` only when useful for focused tests.

### Milestone 6: reliability

Add:

- dead-letter publication;
- bounded consumer retries;
- poison-message handling;
- inbox-based idempotency;
- Kafka health checks;
- Kafka metrics;
- consumer lag visibility.

## Testing strategy

Unit tests must not require Docker or Kafka.

Unit tests cover:

- configuration;
- serialization;
- message keys;
- headers;
- producer adapter behavior;
- consumer runtime behavior;
- offset commit rules;
- error propagation.

Integration tests may use the local Kafka container.

Integration tests cover:

- publishing and consuming an envelope;
- partition-key behavior;
- outbox-to-Kafka flow;
- Kafka-to-dispatcher flow;
- graceful restart;
- redelivery after processing failure.

The full test suite must remain green after every milestone.

## Consequences

Positive consequences:

- durable event transport;
- clean producer and consumer separation;
- process-independent event handling;
- consumer scaling through groups;
- stronger production architecture;
- improved interview and portfolio value.

Negative consequences:

- additional infrastructure;
- eventual consistency;
- duplicate delivery is possible;
- operational complexity increases;
- consumer idempotency becomes mandatory;
- local startup becomes heavier.

## Alternatives considered

### Retain EventRuntime

Rejected for production because it provides no durable or cross-process delivery.

### Redis Streams

Simpler operationally but less aligned with the desired Kafka architecture, partitioning model, ecosystem, and interview objective.

### RabbitMQ

A valid alternative, but Kafka better matches the event-streaming and ordered pipeline requirements of this platform.

### Multiple Kafka topics immediately

Rejected because the current event volume and ownership model do not justify the operational complexity.

## Final decision

Introduce Kafka as the production integration-event transport while preserving the existing domain, application ports, transactional outbox, dispatcher, and application handlers.
