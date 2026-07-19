#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import logging.handlers
import os
import sys


def is_interactive_shell() -> bool:
    """
    Detect interactive shell execution.
    Useful to automatically enable stdout logging locally,
    while cron/background jobs remain file-only.
    """
    return bool(os.environ.get("TERM"))


def setup_logger(
    logfile: str = None,
    stdout: bool = False,
    level=logging.INFO,
    max_bytes: int = 1024 * 1024 * 20,   # 20 MB
    backup_count: int = 10
):
    """
    Configure root logger.

    Features:
    - Rotating file logging
    - Optional stdout logging
    - Production-safe formatting
    - Interactive shell auto-detection
    """

    root = logging.getLogger()
    root.name = "globalroamer_ai"

    # Prevent duplicate handlers
    if root.handlers:
        root.handlers.clear()

    formatter = logging.Formatter(
        fmt=(
            "%(asctime)s "
            "%(process)5d "
            "%(levelname)-5s "
            "%(name)s "
            "%(message)s"
        )
    )

    logging.addLevelName(logging.WARNING, "WARN")
    logging.addLevelName(logging.CRITICAL, "FATAL")

    # Stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)

    # Auto-enable stdout for local interactive runs
    if is_interactive_shell():
        stdout = True

    if logfile is None:
        root.addHandler(stdout_handler)

    else:
        log_dir = os.path.dirname(logfile)

        if not os.path.isdir(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            logfile,
            mode="a",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )

        file_handler.setFormatter(formatter)

        root.addHandler(file_handler)

        if stdout:
            root.addHandler(stdout_handler)

    root.setLevel(level)

    return root
