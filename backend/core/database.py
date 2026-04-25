"""
SQLAlchemy 2.0 database setup.

Architecture
------------
The :class:`Database` class encapsulates an engine and a ``sessionmaker``.
The module-level functions (:func:`init_db`, :func:`get_db`, :func:`get_session`)
are a thin facade over a default process-wide :class:`Database` instance, which
is how FastAPI routes and background services have always consumed this module.

Tests can bypass the singleton by constructing their own :class:`Database`
against a test engine: no global reset gymnastics required.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import settings
from backend.core.logging import get_logger

__all__ = [
    "Base",
    "Database",
    "get_db",
    "get_lock_contention_metrics",
    "get_session",
    "init_db",
    "reset_default_database",
    "reset_lock_contention_metrics",
    "_apply_column_migrations",
]

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ─── Lock Contention Monitoring ──────────────────────────────────────────────

# Global metrics for lock contention tracking
_lock_contention_metrics = {
    "total_lock_waits": 0,
    "total_wait_time_ms": 0.0,
    "max_wait_time_ms": 0.0,
    "waits_over_100ms": 0,
}


def _install_lock_monitoring(engine: Engine) -> None:
    """Install SQLAlchemy event listeners to monitor lock contention.
    
    Tracks lock wait times for SELECT FOR UPDATE queries and logs waits
    exceeding 100ms at WARNING level. Maintains metrics for monitoring.
    """

    @event.listens_for(engine, "before_cursor_execute")
    def _before_execute(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        """Record start time for queries that acquire locks."""
        if "FOR UPDATE" in statement.upper():
            context._lock_start_time = time.time()

    @event.listens_for(engine, "after_cursor_execute")
    def _after_execute(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        """Log and track lock wait times for queries that acquired locks."""
        if hasattr(context, "_lock_start_time"):
            wait_time_sec = time.time() - context._lock_start_time
            wait_time_ms = wait_time_sec * 1000

            # Update metrics
            _lock_contention_metrics["total_lock_waits"] += 1
            _lock_contention_metrics["total_wait_time_ms"] += wait_time_ms
            _lock_contention_metrics["max_wait_time_ms"] = max(
                _lock_contention_metrics["max_wait_time_ms"], wait_time_ms
            )

            # Log waits exceeding 100ms threshold
            if wait_time_ms > 100:
                _lock_contention_metrics["waits_over_100ms"] += 1
                logger.warning(
                    "lock_wait",
                    wait_time_ms=round(wait_time_ms, 2),
                    statement=statement[:200],  # Truncate long statements
                )


def get_lock_contention_metrics() -> dict[str, Any]:
    """Return current lock contention metrics.
    
    Returns:
        Dictionary containing:
        - total_lock_waits: Total number of SELECT FOR UPDATE queries
        - total_wait_time_ms: Cumulative wait time in milliseconds
        - max_wait_time_ms: Maximum single wait time in milliseconds
        - waits_over_100ms: Count of waits exceeding 100ms threshold
        - avg_wait_time_ms: Average wait time (computed)
    """
    metrics = _lock_contention_metrics.copy()
    if metrics["total_lock_waits"] > 0:
        metrics["avg_wait_time_ms"] = round(
            metrics["total_wait_time_ms"] / metrics["total_lock_waits"], 2
        )
    else:
        metrics["avg_wait_time_ms"] = 0.0
    return metrics


def reset_lock_contention_metrics() -> None:
    """Reset lock contention metrics to zero.
    
    Useful for testing or periodic metric collection.
    """
    _lock_contention_metrics["total_lock_waits"] = 0
    _lock_contention_metrics["total_wait_time_ms"] = 0.0
    _lock_contention_metrics["max_wait_time_ms"] = 0.0
    _lock_contention_metrics["waits_over_100ms"] = 0


# ─── Column Migrations (SQLite only) ─────────────────────────────────────────
#
# PostgreSQL uses Alembic for schema changes. For SQLite (used in tests and
# legacy deployments), we apply lightweight ALTER TABLE statements to add
# nullable columns that were introduced after the initial schema was created.

_COLUMN_MIGRATIONS: list[str] = [
    "ALTER TABLE active_image_state ADD COLUMN last_served_hash VARCHAR(64)",
    "ALTER TABLE active_image_state ADD COLUMN last_served_at DATETIME",
]


def _apply_column_migrations(engine: Engine) -> None:
    """Add nullable columns to existing SQLite tables that pre-date them.

    Each statement in ``_COLUMN_MIGRATIONS`` is attempted individually.
    ``OperationalError`` is silently swallowed so the function is idempotent
    (column already exists) and tolerant of missing tables (schema not yet
    created). This is a no-op for non-SQLite engines where Alembic handles
    migrations.

    Args:
        engine: SQLAlchemy engine to run migrations against.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    if not engine.dialect.name.startswith("sqlite"):
        return

    with engine.connect() as conn:
        for stmt in _COLUMN_MIGRATIONS:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except OperationalError:
                conn.rollback()


class Database:
    """Owns an SQLAlchemy :class:`Engine` and a :class:`sessionmaker`.

    The constructor is intentionally lightweight: the engine is created
    immediately but schema creation is deferred to :meth:`create_all`, which
    imports :mod:`backend.models` lazily so that ``Base.metadata`` is
    populated before ``CREATE TABLE`` runs.
    """

    def __init__(self, url: str) -> None:
        self._url: str = url

        # Read connection pool configuration from settings
        pool_size = settings.get("database.pool_size", 5)
        max_overflow = settings.get("database.max_overflow", 10)
        pool_timeout = settings.get("database.pool_timeout", 30)
        pool_recycle = settings.get("database.pool_recycle", 3600)
        pool_pre_ping = settings.get("database.pool_pre_ping", True)
        echo = settings.get("database.echo", False)

        # Build engine kwargs - only include pool parameters for databases that support QueuePool
        # SQLite uses SingletonThreadPool which doesn't support max_overflow/pool_timeout
        engine_kwargs = {
            "echo": echo,
            "pool_pre_ping": pool_pre_ping,
        }

        # Only add QueuePool-specific parameters for non-SQLite databases
        if not url.startswith("sqlite"):
            engine_kwargs.update({
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_timeout": pool_timeout,
                "pool_recycle": pool_recycle,
            })

        # Create engine with connection pooling parameters
        self._engine: Engine = create_engine(url, **engine_kwargs)

        # Log pool configuration at startup
        if url.startswith("sqlite"):
            logger.info(
                "database_pool_configured",
                dialect="sqlite",
                pool_type="SingletonThreadPool",
                pool_pre_ping=pool_pre_ping,
            )
        else:
            logger.info(
                "database_pool_configured",
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=pool_timeout,
                pool_recycle=pool_recycle,
                pool_pre_ping=pool_pre_ping,
                total_capacity=pool_size + max_overflow,
            )

        # Install lock contention monitoring for all database types
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

        Imports :mod:`backend.models` so all ORM classes have had a chance to
        register themselves with ``Base.metadata`` before we issue DDL.
        Then applies lightweight column-level migrations for databases that
        pre-date newly added nullable columns.
        """
        import backend.models  # noqa: F401 : populates Base.metadata

        Base.metadata.create_all(bind=self._engine)

    # -- sessions -------------------------------------------------------------

    def session(self) -> Session:
        """Return a new :class:`Session`. Caller is responsible for closing.
        
        Raises:
            SQLAlchemyTimeoutError: If connection pool is exhausted and timeout is reached.
        """
        try:
            return self._session_factory()
        except SQLAlchemyTimeoutError as e:
            # Pool exhaustion: provide diagnostic information
            pool = self._engine.pool
            pool_size = getattr(pool, 'size', lambda: 'unknown')()
            overflow = getattr(pool, 'overflow', lambda: 'unknown')()
            checkedout = getattr(pool, 'checkedout', lambda: 'unknown')()

            error_msg = (
                f"Database connection pool exhausted. "
                f"Pool size: {pool_size}, overflow: {overflow}, checked out: {checkedout}. "
                f"Consider increasing database.pool_size or database.max_overflow in settings.yaml, "
                f"or investigate long-running transactions."
            )
            logger.error(
                "pool_exhaustion",
                pool_size=pool_size,
                overflow=overflow,
                checkedout=checkedout,
                error=str(e),
            )
            raise SQLAlchemyTimeoutError(error_msg) from e

    def session_scope(self) -> Generator[Session, None, None]:
        """Generator yielding a session that is always closed on exit.
        
        Raises:
            SQLAlchemyTimeoutError: If connection pool is exhausted and timeout is reached.
        """
        sess = self.session()  # Use self.session() to get pool exhaustion handling
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
# from this module. We preserve that API by routing through a default
# :class:`Database` instance created lazily on first use.

_default_database: Database | None = None


def _resolve_url(url: str | None) -> str:
    return url or settings.get("database.url", "sqlite:///./data/cognitive_companion.db")


def _ensure_default(url: str | None = None) -> Database:
    global _default_database
    if _default_database is None:
        _default_database = Database(_resolve_url(url))
    return _default_database


def init_db(url: str | None = None) -> None:
    """Create the default engine, session factory, and all tables.

    Idempotent only when called with no argument. Passing an explicit *url*
    forces a fresh :class:`Database` (useful for CLI scripts and migration
    runners that point at an alternate DB).
    """
    global _default_database
    if url is not None or _default_database is None:
        if _default_database is not None:
            _default_database.dispose()
        _default_database = Database(_resolve_url(url))
    _default_database.create_all()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a DB session and closes it after the request."""
    db = _ensure_default()
    sess = db.session()
    try:
        yield sess
    finally:
        sess.close()


def get_session() -> Session:
    """Non-generator helper for background tasks / services."""
    return _ensure_default().session()


def reset_default_database() -> None:
    """Drop the cached default :class:`Database`.

    Primarily a test-support hook: disposes of the current engine (if any)
    so a subsequent :func:`init_db` call starts from a clean slate.
    """
    global _default_database
    if _default_database is not None:
        _default_database.dispose()
        _default_database = None
