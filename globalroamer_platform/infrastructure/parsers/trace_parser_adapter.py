from __future__ import annotations

from pathlib import Path

from globalroamer_platform.domain.models.raw_trace import RawTrace
from globalroamer_platform.domain.services.trace_parser import TraceParser


class FileTraceParserAdapter:
    """
    Adapt the existing TraceParser to the application ParseTrace contract.
    """

    def __init__(
        self,
        parser: TraceParser | None = None,
    ) -> None:
        self._parser = parser or TraceParser()

    def parse(
        self,
        source: object,
    ) -> RawTrace:
        if isinstance(source, str):
            source = Path(source)

        if not isinstance(source, Path):
            raise TypeError(
                "FileTraceParserAdapter expects a pathlib.Path "
                "or path string"
            )

        return self._parser.parse_file(
            source
        )
