"""
SQLAlchemy 2.0 database setup.

Architecture
------------
The :class:`Database` class encapsulates an engine, a ``sessionmaker``, and
the SQLite pragma wiring. The module-level functions (:func:`init_db`,
:func:`get_db`, :func:`get_session`) are a thin facade over a default
process-wide :class:`Database` instance, which is how FastAPI routes and
background services have always consumed this module.

Tests can bypass the singleton by constructing their own :class:`Database`
against an in-memory engine: no global reset gymnastics required.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import settings

__all__ = ["Base", "Database", "get_db", "get_session", "init_db", "reset_default_database"]


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


_COLUMN_MIGRATIONS: tuple[str, ...] = (
    # Each statement adds a nullable column that may not yet exist in an
    # already-running database.  The statements are idempotent: if the column
    # is already present the OperationalError is swallowed and the transaction
    # is rolled back cleanly.
    "ALTER TABLE active_image_state ADD COLUMN last_served_hash VARCHAR(64)",
    "ALTER TABLE active_image_state ADD COLUMN last_served_at DATETIME",
    # Camera-topology fields on PersonLocationHistory (added 2026-04-13).
    "ALTER TABLE person_location_history ADD COLUMN direction_semantic VARCHAR(32)",
    "ALTER TABLE person_location_history ADD COLUMN from_room_id INTEGER REFERENCES rooms(id)",
    "ALTER TABLE person_location_history ADD COLUMN from_room_name VARCHAR(128)",
    # Duration-aware activity session fields on person_activities (added 2026-04-16).
    "ALTER TABLE person_activities ADD COLUMN duration_minutes INTEGER",
    "ALTER TABLE person_activities ADD COLUMN session_id VARCHAR(64)",
    # Observation backlink for auditability chain (added 2026-04-16).
    "ALTER TABLE person_activities ADD COLUMN observation_id INTEGER REFERENCES scene_observations(id)",
)


def _apply_column_migrations(engine: Engine) -> None:
    """Add new nullable columns to existing tables without Alembic.

    Each statement is executed in its own savepoint so a ``column already
    exists`` error on one column does not abort the rest.
    """
    with engine.connect() as conn:
        for stmt in _COLUMN_MIGRATIONS:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except OperationalError:
                # Column already present: safe to ignore.
                conn.rollback()


def _install_sqlite_pragmas(engine: Engine) -> None:
    """Enable WAL journaling and foreign-key enforcement on SQLite engines."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn: Any, _: Any) -> None:
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def _ensure_sqlite_dir(url: str) -> None:
    """Create the parent directory of a SQLite file URL if needed."""
    if not url.startswith("sqlite"):
        return
    # sqlite:///./path or sqlite:////abs/path  both split on the final ///
    path_part = url.split("///", 1)[-1]
    if not path_part or path_part == ":memory:":
        return
    Path(path_part).parent.mkdir(parents=True, exist_ok=True)


class Database:
    """Owns an SQLAlchemy :class:`Engine` and a :class:`sessionmaker`.

    The constructor is intentionally lightweight: the engine is created
    immediately but schema creation is deferred to :meth:`create_all`, which
    imports :mod:`backend.models` lazily so that ``Base.metadata`` is
    populated before ``CREATE TABLE`` runs.
    """

    def __init__(self, url: str) -> None:
        self._url: str = url
        _ensure_sqlite_dir(url)
        self._engine: Engine = create_engine(url, echo=False, pool_pre_ping=True)
        if url.startswith("sqlite"):
            _install_sqlite_pragmas(self._engine)
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
        _apply_column_migrations(self._engine)

    # -- sessions -------------------------------------------------------------

    def session(self) -> Session:
        """Return a new :class:`Session`. Caller is responsible for closing."""
        return self._session_factory()

    def session_scope(self) -> Generator[Session, None, None]:
        """Generator yielding a session that is always closed on exit."""
        sess = self._session_factory()
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
