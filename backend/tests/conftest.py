"""Shared pytest fixtures for the backend test suite."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.core.database import Base


@pytest.fixture(scope="function")
def db_engine():
    """In-memory SQLite engine with the full ORM schema.

    The ``event_logs`` / ``workflow_executions`` tables have a circular FK
    dependency that prevents SQLAlchemy from computing a DROP order for
    SQLite.  We disable FK enforcement before teardown to avoid this.
    """
    import backend.models  # noqa: F401  registers all models with Base

    from sqlalchemy import event, text

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine

    # Disable FK checks so the circular dependency doesn't block DROP TABLE.
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.commit()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Transactional DB session that is rolled back after each test."""
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session: Session = factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="function")
def db_factory(db_engine):
    """Session factory returning sessions bound to the in-memory engine."""
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    def _make() -> Session:
        return factory()

    return _make
