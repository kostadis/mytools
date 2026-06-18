"""Logging configuration for the notetaker pipeline.

`configure_logging()` sets up a single structlog processing chain that
fans every event out to two sinks via stdlib `logging`'s handler model:

  - `sys.stderr`  — human-readable (or JSON, when `fmt="json"`).
  - `<run-log>`   — JSON-lines, line-buffered, flushed per record.

The file sink is opt-in via the `file_path` parameter. When None or when
the file cannot be opened, the pipeline degrades to stderr-only without
raising — `cli._setup()` surfaces a single warning to the user.

Records emitted by SIGKILL'd or OOM'd runs still land on disk because the
file handler flushes after every emit (FR-007).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import structlog


class _FlushingFileHandler(logging.FileHandler):
    """FileHandler that flushes per emit so a killed process leaves the most
    recent record on disk (FR-007 / SC-003)."""

    def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
        super().emit(record)
        try:
            self.flush()
        except Exception:
            pass


def configure_logging(
    level: str = "INFO",
    fmt: str = "console",
    file_path: Optional[Path] = None,
) -> None:
    """Configure structlog for stderr (always) plus an optional file sink."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    pre_chain = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if fmt == "json":
        console_renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        console_renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    file_renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.ExceptionRenderer(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(log_level)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(log_level)
    stderr_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=console_renderer,
            foreign_pre_chain=pre_chain,
        )
    )
    root.addHandler(stderr_handler)

    if file_path is not None:
        try:
            file_handler = _FlushingFileHandler(file_path, encoding="utf-8")
        except OSError as exc:
            print(
                f"[notetaker] WARNING: cannot open log file {file_path} "
                f"({type(exc).__name__}: {exc}); continuing with stderr only",
                file=sys.stderr,
            )
        else:
            file_handler.setLevel(log_level)
            file_handler.setFormatter(
                structlog.stdlib.ProcessorFormatter(
                    processor=file_renderer,
                    foreign_pre_chain=pre_chain,
                )
            )
            root.addHandler(file_handler)


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    return structlog.get_logger(name)


def bind_contextvars(**kwargs) -> None:
    """Bind key-value pairs to the current async/thread context for all subsequent log calls."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_contextvars() -> None:
    structlog.contextvars.clear_contextvars()
