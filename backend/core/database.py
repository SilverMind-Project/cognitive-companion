"""
SQLAlchemy 2.0 database setup.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def _get_engine(url: str | None = None):
    db_url = url or settings.get("database.url", "sqlite:///./data/cognitive_companion.db")

    # Ensure the directory for SQLite exists
    if db_url.startswith("sqlite"):
        db_path = db_url.split("///")[-1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(db_url, echo=False, pool_pre_ping=True)

    # Enable WAL mode and foreign keys for SQLite
    if db_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def init_db(url: str | None = None) -> None:
    """Create the engine, session factory, and all tables."""
    global _engine, _SessionLocal

    _engine = _get_engine(url)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)

    # Import all models so Base.metadata knows about them
    import backend.models  # noqa: F401

    Base.metadata.create_all(bind=_engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency – yields a DB session and closes it after the request."""
    if _SessionLocal is None:
        init_db()
    db = _SessionLocal()  # type: ignore[misc]
    try:
        yield db
    finally:
        db.close()


def get_session() -> Session:
    """Non-generator helper for background tasks / services."""
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()  # type: ignore[misc]
