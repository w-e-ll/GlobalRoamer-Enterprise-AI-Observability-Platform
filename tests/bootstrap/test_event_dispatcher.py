from __future__ import annotations

from unittest.mock import Mock

from globalroamer_platform.bootstrap.event_dispatcher import (
    TRACE_ARTIFACT_RECEIVED,
    TRACE_CHUNKED,
    TRACE_NORMALIZED,
    TRACE_PARSED,
    build_event_dispatcher,
)


def test_build_event_dispatcher_registers_trace_pipeline() -> None:
    session_factory = Mock()

    dispatcher = build_event_dispatcher(
        session_factory=session_factory,
        parser_handler_factory=Mock(),
        normalizer_handler_factory=Mock(),
        chunk_handler_factory=Mock(),
        embedding_handler_factory=Mock(),
    )

    assert dispatcher.registered_event_types == (
        TRACE_ARTIFACT_RECEIVED,
        TRACE_CHUNKED,
        TRACE_NORMALIZED,
        TRACE_PARSED,
    )
