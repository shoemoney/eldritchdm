"""
EldritchDM structured logging.

Configures structlog with either JSON (production) or ConsoleRenderer (dev)
output, based on the `fmt` argument (or LOG_FORMAT env var).

Secrets scrubbing: any structlog event dict key matching *token*, *secret*,
or *key* is redacted before rendering (T-01-02 mitigation).

IMPORTANT: This module must NOT import eldritch_dm.persistence,
           eldritch_dm.mcp, or eldritch_dm.safety (import-linter enforced).
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Literal

import structlog
from structlog.types import EventDict, WrappedLogger

# ── Secret scrubbing processor ────────────────────────────────────────────────

_SCRUB_KEYS = frozenset({"token", "secret", "key", "password", "passwd", "auth"})


def _scrub_secrets(
    _logger: WrappedLogger,
    _method: str,
    event_dict: EventDict,
) -> EventDict:
    """Redact values whose key contains a sensitive word."""
    for k in list(event_dict.keys()):
        if any(sensitive in k.lower() for sensitive in _SCRUB_KEYS):
            event_dict[k] = "***REDACTED***"
    return event_dict


# ── Public API ────────────────────────────────────────────────────────────────


def configure_logging(
    level: str = "INFO",
    fmt: Literal["json", "console"] = "console",
    log_file: str | None = None,
) -> None:
    """Configure structlog for the process.

    Call once at startup (e.g., in run.py or bootstrap.main()).

    Args:
        level: Python logging level name ("DEBUG", "INFO", "WARNING", "ERROR").
        fmt:   "json" for production JSON output; "console" for colored dev output.
        log_file: Optional path to write logs to in addition to stderr.
    """
    # Configure stdlib logging as the underlying output layer
    log_level_int = getattr(logging, level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        format="%(message)s",
        level=log_level_int,
        handlers=handlers,
        force=True,
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _scrub_secrets,
        structlog.processors.StackInfoRenderer(),
    ]

    if fmt == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)


def get_logger(name: str = "eldritch_dm") -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for the given name.

    Example::

        log = get_logger(__name__)
        log.info("session_started", channel_id="123", campaign="Lost Mines")
    """
    return structlog.get_logger(name)  # type: ignore[return-value]
