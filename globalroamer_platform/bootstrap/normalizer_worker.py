"""Bootstrap wiring for the normalizer worker."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from globalroamer_platform.application.traces.normalize_trace import (
    NormalizeTrace,
)
from globalroamer_platform.domain.services.trace_normalizer import (
    TraceNormalizer,
)
from globalroamer_platform.infrastructure.database.repositories.sqlalchemy_outbox_repository import (
    SQLAlchemyOutboxRepository,
)
from globalroamer_platform.infrastructure.persistence.operational_event_store import (
    OperationalEventStore,
)
from globalroamer_platform.infrastructure.persistence.parsed_trace_store import (
    ParsedTraceStore,
)
from globalroamer_platform.runtime.session_scoped_event_handler import (
    EventHandlerFactory,
)
from globalroamer_platform.workers.normalizer_worker import (
    NormalizerWorker,
)


def build_normalizer_worker(
    *,
    session: AsyncSession,
) -> NormalizerWorker:
    """
    Build the complete normalizer worker dependency graph.

    The same AsyncSession is shared by:

    - ParsedTraceStore
    - OperationalEventStore
    - SQLAlchemyOutboxRepository

    This allows normalized operational events and the outgoing transactional
    outbox message to participate in the transaction owned by the runtime.
    """
    trace_normalizer = TraceNormalizer()

    normalize_trace = NormalizeTrace(
        trace_normalizer=trace_normalizer,
    )

    parsed_trace_store = ParsedTraceStore(
        session=session,
    )

    operational_event_store = OperationalEventStore(
        session=session,
    )

    outbox_repository = SQLAlchemyOutboxRepository(
        session=session,
    )

    return NormalizerWorker(
        normalize_trace=normalize_trace,
        parsed_trace_store=parsed_trace_store,
        operational_event_store=operational_event_store,
        outbox_repository=outbox_repository,
    )


def build_normalizer_handler_factory() -> EventHandlerFactory:
    """
    Build a session-aware NormalizerWorker factory.

    SessionScopedEventHandler invokes the returned factory once per
    dispatched event, supplying the transaction-bound AsyncSession.
    """

    def factory(
        session: AsyncSession,
    ) -> NormalizerWorker:
        return build_normalizer_worker(
            session=session,
        )

    return factory
