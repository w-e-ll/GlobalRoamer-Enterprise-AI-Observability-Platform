"""Composition root for transactional integration-event dispatching."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from globalroamer_platform.bootstrap.parser_worker import (
    build_parser_worker,
)
from globalroamer_platform.domain.events.event_types import (
    TRACE_ARTIFACT_RECEIVED,
    TRACE_CHUNKED,
    TRACE_NORMALIZED,
    TRACE_PARSED,
)
from globalroamer_platform.runtime.event_dispatcher import (
    EventDispatcher,
)
from globalroamer_platform.runtime.session_scoped_event_handler import (
    EventHandlerFactory,
    SessionScopedEventHandler,
)
from globalroamer_platform.workers.parser_worker import (
    ParserWorker,
)


def build_event_dispatcher(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    parser_handler_factory: EventHandlerFactory,
    normalizer_handler_factory: EventHandlerFactory,
    chunk_handler_factory: EventHandlerFactory,
    embedding_handler_factory: EventHandlerFactory,
) -> EventDispatcher:
    """
    Build the transactional integration-event dispatcher.

    Every registered handler executes in a fresh SQLAlchemy session.
    Successful handling commits the transaction. Failure or cancellation
    rolls it back before propagating the original exception.

    Event routing:

        TRACE_ARTIFACT_RECEIVED -> ParserWorker
        TRACE_PARSED            -> NormalizerWorker
        TRACE_NORMALIZED        -> ChunkWorker
        TRACE_CHUNKED           -> EmbeddingWorker
    """
    dispatcher = EventDispatcher()

    parser_handler = SessionScopedEventHandler(
        session_factory=session_factory,
        handler_factory=parser_handler_factory,
    )
    normalizer_handler = SessionScopedEventHandler(
        session_factory=session_factory,
        handler_factory=normalizer_handler_factory,
    )
    chunk_handler = SessionScopedEventHandler(
        session_factory=session_factory,
        handler_factory=chunk_handler_factory,
    )
    embedding_handler = SessionScopedEventHandler(
        session_factory=session_factory,
        handler_factory=embedding_handler_factory,
    )

    dispatcher.register(
        event_type=TRACE_ARTIFACT_RECEIVED,
        handler=parser_handler.handle,
    )
    dispatcher.register(
        event_type=TRACE_PARSED,
        handler=normalizer_handler.handle,
    )
    dispatcher.register(
        event_type=TRACE_NORMALIZED,
        handler=chunk_handler.handle,
    )
    dispatcher.register(
        event_type=TRACE_CHUNKED,
        handler=embedding_handler.handle,
    )

    return dispatcher


def build_parser_handler_factory(
    *,
    trace_directory: Path,
    mapping_configuration_path: Path,
    source_timezone: str = "UTC",
    target_timezone: str = "UTC",
    supported_extensions: list[str] | None = None,
    max_file_size_mb: int = 100,
) -> EventHandlerFactory:
    """
    Build a session-aware ParserWorker factory for dispatcher wiring.

    SessionScopedEventHandler invokes the returned factory once per event,
    supplying the transaction-bound AsyncSession for that event.
    """

    def factory(
        session: AsyncSession,
    ) -> ParserWorker:
        return build_parser_worker(
            session=session,
            trace_directory=trace_directory,
            mapping_configuration_path=mapping_configuration_path,
            source_timezone=source_timezone,
            target_timezone=target_timezone,
            supported_extensions=supported_extensions,
            max_file_size_mb=max_file_size_mb,
        )

    return factory
