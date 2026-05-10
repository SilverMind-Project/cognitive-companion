"""
SQLAlchemy 2.0 database setup for PostgreSQL.

Architecture
------------
The :class:`Database` class encapsulates an engine and a ``sessionmaker``.
The module-level functions (:func:`init_db`, :func:`get_db`, :func:`get_session`)
are a thin facade over a default process-wide :class:`Database` instance.

Schema migrations are managed exclusively by Alembic.  Never call
``create_all()`` in production; use ``make migrate`` (``alembic upgrade head``).

Tests construct their own :class:`Database` against a PostgreSQL testcontainer
via the ``db_engine`` / ``db_session`` / ``db_factory`` fixtures in
``backend/tests/conftest.py``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, create_engine, event, func
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.time import UTCDateTime

__all__ = [
    "Base",
    "Database",
    "TimestampMixin",
    "UTCDateTime",
    "get_db",
    "get_session",
    "init_db",
    "reset_default_database",
    "transaction",
]

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class TimestampMixin:
    """Mixin providing ``created_at`` and ``updated_at`` columns.

    ``created_at`` is set once on insert (server-side default).
    ``updated_at`` is set on insert and updated on every row change via
    the SQLAlchemy ``onupdate`` hook.  Models that need a different
    ``updated_at`` contract (e.g. non-null with a server default) can
    override the column in the model body.
    """

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True, onupdate=func.now()
    )


@contextmanager
def transaction(db_factory: Callable[[], Session]) -> Generator[Session]:
    """Context manager that yields a DB session and commits on success.

    Rolls back on exception and always closes the session in a finally block.
    Use in services that follow the session-per-call pattern.

    Usage::

        with transaction(self._db_session_factory) as db:
            row = db.get(Model, id)
            row.field = value
    """
    db = db_factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ─── Lock Contention Monitoring ──────────────────────────────────────────────

_lock_contention_metrics = {
    "total_lock_waits": 0,
    "total_wait_time_ms": 0.0,
    "max_wait_time_ms": 0.0,
    "waits_over_100ms": 0,
}


def _install_lock_monitoring(engine: Engine) -> None:
    """Install SQLAlchemy event listeners to monitor lock contention.

    Tracks lock wait times for SELECT FOR UPDATE queries and logs waits
    exceeding 100 ms at WARNING level.
    """

    @event.listens_for(engine, "before_cursor_execute")
    def _before_execute(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        if "FOR UPDATE" in statement.upper():
            context._lock_start_time = time.time()

    @event.listens_for(engine, "after_cursor_execute")
    def _after_execute(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        if hasattr(context, "_lock_start_time"):
            wait_time_ms = (time.time() - context._lock_start_time) * 1000

            _lock_contention_metrics["total_lock_waits"] += 1
            _lock_contention_metrics["total_wait_time_ms"] += wait_time_ms
            _lock_contention_metrics["max_wait_time_ms"] = max(
                _lock_contention_metrics["max_wait_time_ms"], wait_time_ms
            )

            if wait_time_ms > 100:
                _lock_contention_metrics["waits_over_100ms"] += 1
                logger.warning(
                    "lock_wait",
                    wait_time_ms=round(wait_time_ms, 2),
                    statement=statement[:200],
                )


def get_lock_contention_metrics() -> dict[str, Any]:
    """Return a snapshot of current lock contention metrics."""
    metrics = _lock_contention_metrics.copy()
    total = metrics["total_lock_waits"]
    metrics["avg_wait_time_ms"] = round(metrics["total_wait_time_ms"] / total, 2) if total > 0 else 0.0
    return metrics


def reset_lock_contention_metrics() -> None:
    """Reset lock contention metrics to zero (useful for periodic collection)."""
    _lock_contention_metrics["total_lock_waits"] = 0
    _lock_contention_metrics["total_wait_time_ms"] = 0.0
    _lock_contention_metrics["max_wait_time_ms"] = 0.0
    _lock_contention_metrics["waits_over_100ms"] = 0


class Database:
    """Owns an SQLAlchemy :class:`Engine` and a :class:`sessionmaker`.

    The constructor is intentionally lightweight: the engine is created
    immediately but schema creation is deferred to :meth:`create_all`, which
    imports :mod:`backend.models` lazily so that ``Base.metadata`` is
    populated before ``CREATE TABLE`` runs.

    In production, prefer Alembic migrations over :meth:`create_all`.
    """

    def __init__(self, url: str) -> None:
        self._url: str = url

        pool_size = settings.get("database.pool_size", 5)
        max_overflow = settings.get("database.max_overflow", 10)
        pool_timeout = settings.get("database.pool_timeout", 30)
        pool_recycle = settings.get("database.pool_recycle", 3600)
        pool_pre_ping = settings.get("database.pool_pre_ping", True)
        echo = settings.get("database.echo", False)

        # StaticPool (SQLite default) and NullPool don't accept pool_size/max_overflow/pool_timeout.
        # Build the engine with pool params first; if the pool type rejects them, retry without.
        engine_kwargs: dict[str, Any] = {
            "url": url,
            "echo": echo,
            "pool_pre_ping": pool_pre_ping,
            "pool_recycle": pool_recycle,
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_timeout": pool_timeout,
        }

        try:
            self._engine: Engine = create_engine(**engine_kwargs)
        except TypeError:
            del engine_kwargs["pool_size"]
            del engine_kwargs["max_overflow"]
            del engine_kwargs["pool_timeout"]
            self._engine = create_engine(**engine_kwargs)

        pool_type = type(self._engine.pool).__name__
        if pool_type == "QueuePool":
            logger.info(
                "database_pool_configured",
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=pool_timeout,
                pool_recycle=pool_recycle,
                pool_pre_ping=pool_pre_ping,
                total_capacity=pool_size + max_overflow,
            )

        _install_lock_monitoring(self._engine)

        self._session_factory: sessionmaker[Session] = sessionmaker(
            bind=self._engine,
            autoflush=False,
            expire_on_commit=False,
        )

    # -- properties -----------------------------------------------------------

    @property
    def url(self) -> str:
        return self._url

    @property
    def engine(self) -> Engine:
        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        return self._session_factory

    # -- schema ---------------------------------------------------------------

    def create_all(self) -> None:
        """Create every table registered on :class:`Base`.

        Imports :mod:`backend.models` so all ORM classes register themselves
        with ``Base.metadata`` before DDL is issued.

        Prefer Alembic migrations (``make migrate``) in production.
        """
        import backend.models  # noqa: F401 — populates Base.metadata

        Base.metadata.create_all(bind=self._engine)

    # -- sessions -------------------------------------------------------------

    def session(self) -> Session:
        """Return a new :class:`Session`. Caller is responsible for closing.

        Raises:
            SQLAlchemyTimeoutError: If the connection pool is exhausted.
        """
        try:
            return self._session_factory()
        except SQLAlchemyTimeoutError as e:
            pool = self._engine.pool
            pool_size = getattr(pool, "size", lambda: "unknown")()
            overflow = getattr(pool, "overflow", lambda: "unknown")()
            checkedout = getattr(pool, "checkedout", lambda: "unknown")()

            logger.error(
                "pool_exhaustion",
                pool_size=pool_size,
                overflow=overflow,
                checkedout=checkedout,
                error=str(e),
            )
            raise SQLAlchemyTimeoutError(
                f"Database connection pool exhausted. "
                f"Pool size: {pool_size}, overflow: {overflow}, checked out: {checkedout}. "
                f"Consider increasing database.pool_size or database.max_overflow in settings.yaml."
            ) from e

    def session_scope(self) -> Generator[Session]:
        """Generator yielding a session that is always closed on exit."""
        sess = self.session()
        try:
            yield sess
        finally:
            sess.close()

    def dispose(self) -> None:
        """Release the underlying connection pool. Safe to call repeatedly."""
        self._engine.dispose()


# ─── Module-level facade ─────────────────────────────────────────────────────
#
# The rest of the backend imports ``init_db`` / ``get_db`` / ``get_session``
# from this module.  These route through a default process-wide
# :class:`Database` instance created lazily on first use.

_default_database: Database | None = None


def _resolve_url(url: str | None) -> str:
    resolved = url or settings.get("database.url")
    if not resolved:
        raise RuntimeError(
            "database.url is not configured. "
            "Set it in config/settings.yaml or via the POSTGRES_* environment variables."
        )
    return resolved


def _ensure_default(url: str | None = None) -> Database:
    global _default_database
    if _default_database is None:
        _default_database = Database(_resolve_url(url))
    return _default_database


def _run_alembic_migrations() -> None:
    """Apply pending Alembic migrations at startup.

    Idempotent for fresh databases (creates all tables) and existing
    databases (skips already-applied revisions).  The sqlalchemy.url is
    left blank so env.py populates it from settings.yaml.
    """
    from pathlib import Path

    import alembic.command
    import alembic.config

    alembic_dir = Path(__file__).resolve().parent.parent / "alembic"
    alembic_cfg = alembic.config.Config()
    alembic_cfg.set_main_option("script_location", str(alembic_dir))
    alembic_cfg.set_main_option("sqlalchemy.url", "")

    alembic.command.upgrade(alembic_cfg, "head")
    logger.info("alembic_migrations_complete")


def init_db(url: str | None = None, *, run_migrations: bool = True) -> None:
    """Create the default engine, session factory, and schema.

    Schema is applied via Alembic (``alembic upgrade head``), which is
    safe for both fresh and existing databases.  Pass *run_migrations=False*
    for tools that manage migrations separately (e.g. the Alembic CLI itself).

    Passing an explicit *url* forces a fresh :class:`Database`.
    """
    global _default_database
    if url is not None or _default_database is None:
        if _default_database is not None:
            _default_database.dispose()
        _default_database = Database(_resolve_url(url))
    if run_migrations:
        _run_alembic_migrations()


def get_db() -> Generator[Session]:
    """FastAPI dependency: yields a DB session and closes it after the request."""
    db = _ensure_default()
    sess = db.session()
    try:
        yield sess
    finally:
        sess.close()


def get_session() -> Session:
    """Non-generator helper for background tasks and services."""
    return _ensure_default().session()


def reset_default_database() -> None:
    """Drop the cached default :class:`Database`.

    Test-support hook: disposes the current engine so a subsequent
    :func:`init_db` call starts from a clean slate.
    """
    global _default_database
    if _default_database is not None:
        _default_database.dispose()
        _default_database = None
