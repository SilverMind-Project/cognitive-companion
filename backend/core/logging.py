"""
Logging setup using the Python standard library.

Provides a ``get_logger()`` helper whose returned object accepts structlog-style
keyword arguments (``logger.info("event", key=val)``).  Keywords are appended to
the log line as ``key=val`` pairs so call sites throughout the codebase need no
changes when switching from structlog.
"""

from __future__ import annotations

import logging
import sys
from typing import Any


class _BoundLogger:
    """Thin wrapper around a stdlib logger that accepts keyword context.

    Usage matches the structlog bound-logger API::

        logger = get_logger(__name__)
        logger.info("sensor_event", sensor_id=sid, room="Kitchen")
        # → "sensor_event sensor_id=cam1 room=Kitchen"
    """

    def __init__(self, inner: logging.Logger) -> None:
        self._inner = inner

    # -- helpers --------------------------------------------------------------

    def _msg(self, event: str, kwargs: dict[str, Any]) -> str:
        if not kwargs:
            return event
        pairs = " ".join(f"{k}={v}" for k, v in kwargs.items())
        return f"{event} {pairs}"

    # -- log methods ----------------------------------------------------------

    def debug(self, event: str, **kwargs: Any) -> None:
        if self._inner.isEnabledFor(logging.DEBUG):
            self._inner.debug(self._msg(event, kwargs), stacklevel=2)

    def info(self, event: str, **kwargs: Any) -> None:
        if self._inner.isEnabledFor(logging.INFO):
            self._inner.info(self._msg(event, kwargs), stacklevel=2)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._inner.warning(self._msg(event, kwargs), stacklevel=2)

    # alias
    warn = warning

    def error(self, event: str, **kwargs: Any) -> None:
        self._inner.error(self._msg(event, kwargs), stacklevel=2)

    def exception(self, event: str, **kwargs: Any) -> None:
        """Log at ERROR level and include the current exception traceback."""
        self._inner.exception(self._msg(event, kwargs), stacklevel=2)

    def critical(self, event: str, **kwargs: Any) -> None:
        self._inner.critical(self._msg(event, kwargs), stacklevel=2)


def setup_logging() -> None:
    """Configure stdlib logging for the application."""
    from backend.core.config import settings

    level_name = settings.get("app.log_level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        format=fmt,
        datefmt=datefmt,
        stream=sys.stdout,
        level=level,
        force=True,
    )

    # Silence noisy third-party loggers
    for name in ("httpx", "httpcore", "urllib3", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> _BoundLogger:
    """Return a bound logger for *name* (typically ``__name__``)."""
    return _BoundLogger(logging.getLogger(name))
