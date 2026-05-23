"""
Logging setup using the Python standard library.

Provides a :func:`get_logger` helper whose returned object accepts
structlog-style keyword arguments (``logger.info("event", key=val)``).
Keywords are appended to the log line as ``key=val`` pairs, so call sites
throughout the codebase need no changes when switching from structlog.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, TextIO

__all__ = ["BoundLogger", "get_logger", "setup_logging"]

#: Third-party loggers that are too chatty at INFO level and get silenced.
_NOISY_LOGGERS: tuple[str, ...] = (
    "httpx",
    "httpcore",
    "urllib3",
    "sqlalchemy.engine",
)

_DEFAULT_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"


class BoundLogger:
    """Thin wrapper around a stdlib logger that accepts keyword context.

    Usage matches the structlog bound-logger API::

        logger = get_logger(__name__)
        logger.info("sensor_event", sensor_id=sid, room="Kitchen")
        # → "sensor_event sensor_id=cam1 room=Kitchen"
    """

    __slots__ = ("_inner",)

    def __init__(self, inner: logging.Logger) -> None:
        self._inner = inner

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _format(event: str, kwargs: dict[str, Any]) -> str:
        if not kwargs:
            return event
        pairs = " ".join(f"{k}={v}" for k, v in kwargs.items())
        return f"{event} {pairs}"

    # -- log methods ----------------------------------------------------------

    def debug(self, event: str, **kwargs: Any) -> None:
        if self._inner.isEnabledFor(logging.DEBUG):
            self._inner.debug(self._format(event, kwargs), stacklevel=2)

    def info(self, event: str, **kwargs: Any) -> None:
        if self._inner.isEnabledFor(logging.INFO):
            self._inner.info(self._format(event, kwargs), stacklevel=2)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._inner.warning(self._format(event, kwargs), stacklevel=2)

    # alias for stdlib parity
    warn = warning

    def error(self, event: str, **kwargs: Any) -> None:
        self._inner.error(self._format(event, kwargs), stacklevel=2)

    def exception(self, event: str, **kwargs: Any) -> None:
        """Log at ERROR level and include the current exception traceback."""
        self._inner.exception(self._format(event, kwargs), stacklevel=2)

    def critical(self, event: str, **kwargs: Any) -> None:
        self._inner.critical(self._format(event, kwargs), stacklevel=2)


def setup_logging(
    level: str | int | None = None,
    *,
    stream: TextIO | None = None,
    fmt: str = _DEFAULT_FORMAT,
    datefmt: str = _DEFAULT_DATEFMT,
) -> None:
    """Configure stdlib logging for the application.

    Parameters are all optional:

    * ``level``: log level name or numeric level. If None, reads
      ``app.log_level`` from the application settings (default ``INFO``).
    * ``stream``: destination stream, defaults to ``sys.stdout``.
    * ``fmt`` / ``datefmt``: formatter overrides.
    """
    from backend.core.config import settings

    if level is None:
        level_name = settings.as_str("logging.level").upper()
        resolved_level = getattr(logging, level_name, logging.INFO)
    elif isinstance(level, str):
        resolved_level = getattr(logging, level.upper(), logging.INFO)
    else:
        resolved_level = level

    logging.basicConfig(
        format=fmt,
        datefmt=datefmt,
        stream=stream or sys.stdout,
        level=resolved_level,
        force=True,
    )

    # Silence noisy third-party loggers
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> BoundLogger:
    """Return a bound logger for *name* (typically ``__name__``)."""
    return BoundLogger(logging.getLogger(name))
