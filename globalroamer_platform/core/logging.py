# globalroamer_platform/core/logging.py

from __future__ import annotations

import logging
import logging.handlers
import sys
import time
from contextvars import ContextVar
from pathlib import Path

import json
from datetime import datetime, timezone

from globalroamer_platform.core.config import LoggingSettings


correlation_id_context: ContextVar[str] = ContextVar(
    "correlation_id",
    default="-",
)

tenant_id_context: ContextVar[str] = ContextVar(
    "tenant_id",
    default="-",
)

trace_id_context: ContextVar[str] = ContextVar(
    "trace_id",
    default="-",
)

stage_context: ContextVar[str] = ContextVar(
    "stage",
    default="-",
)


VALID_LOG_LEVELS = {
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
}


class ContextFilter(logging.Filter):
    """Add request and processing context to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_context.get()
        record.tenant_id = tenant_id_context.get()
        record.trace_id = trace_id_context.get()
        record.stage = stage_context.get()

        return True


def _get_log_level(level_name: str) -> int:
    normalized_level = level_name.strip().upper()

    if normalized_level not in VALID_LOG_LEVELS:
        supported_levels = ", ".join(
            sorted(VALID_LOG_LEVELS)
        )

        raise ValueError(
            f"Unsupported log level: {level_name}. "
            f"Supported levels: {supported_levels}"
        )

    return getattr(
        logging,
        normalized_level,
    )


def _create_text_formatter() -> logging.Formatter:
    formatter = logging.Formatter(
        fmt=(
            "%(asctime)s "
            "%(process)5d "
            "%(levelname)-8s "
            "%(name)s "
            "correlation_id=%(correlation_id)s "
            "tenant_id=%(tenant_id)s "
            "trace_id=%(trace_id)s "
            "stage=%(stage)s "
            "%(message)s"
        ),
    )

    formatter.converter = time.gmtime

    return formatter


class JsonFormatter(logging.Formatter):
    """Lightweight JSON formatter for structured logs."""

    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "process_id": record.process,
            "correlation_id": getattr(
                record,
                "correlation_id",
                "-",
            ),
            "tenant_id": getattr(
                record,
                "tenant_id",
                "-",
            ),
            "trace_id": getattr(
                record,
                "trace_id",
                "-",
            ),
            "stage": getattr(
                record,
                "stage",
                "-",
            ),
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(
                record.exc_info
            )

        return json.dumps(
            payload,
            ensure_ascii=False,
        )


def _create_json_formatter() -> logging.Formatter:
    return JsonFormatter()


def _create_formatter(
    settings: LoggingSettings,
) -> logging.Formatter:
    if settings.format == "json":
        return _create_json_formatter()

    return _create_text_formatter()


def _configure_handler(
    *,
    handler: logging.Handler,
    formatter: logging.Formatter,
    context_filter: ContextFilter,
) -> None:
    handler.setFormatter(formatter)
    handler.addFilter(context_filter)


def _configure_library_loggers() -> None:
    logging.getLogger("uvicorn.access").setLevel(
        logging.INFO
    )
    logging.getLogger("uvicorn.error").setLevel(
        logging.INFO
    )

    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.WARNING
    )
    logging.getLogger("httpx").setLevel(
        logging.WARNING
    )
    logging.getLogger("urllib3").setLevel(
        logging.WARNING
    )
    logging.getLogger("asyncio").setLevel(
        logging.WARNING
    )
    logging.getLogger("chromadb").setLevel(
        logging.WARNING
    )
    logging.getLogger("openai").setLevel(
        logging.WARNING
    )


def setup_logging(
    *,
    settings: LoggingSettings,
    log_file: Path | None = None,
    stdout: bool = True,
) -> None:
    """
    Configure application logging.

    Supports human-readable text logs and structured JSON logs,
    contextual fields, stdout output and rotating log files.
    """

    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    level = _get_log_level(
        settings.level
    )
    formatter = _create_formatter(
        settings
    )
    context_filter = ContextFilter()

    if stdout:
        stream_handler = logging.StreamHandler(
            sys.stdout
        )

        _configure_handler(
            handler=stream_handler,
            formatter=formatter,
            context_filter=context_filter,
        )

        root_logger.addHandler(
            stream_handler
        )

    if log_file is not None:
        log_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        file_handler = (
            logging.handlers.RotatingFileHandler(
                filename=log_file,
                maxBytes=(
                    settings.rotation_mb
                    * 1024
                    * 1024
                ),
                backupCount=settings.backup_count,
                encoding="utf-8",
            )
        )

        _configure_handler(
            handler=file_handler,
            formatter=formatter,
            context_filter=context_filter,
        )

        root_logger.addHandler(
            file_handler
        )

    root_logger.setLevel(
        level
    )

    _configure_library_loggers()
