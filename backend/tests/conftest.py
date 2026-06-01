"""Shared pytest fixtures for the backend test suite.

Container lifecycle guarantees
------------------------------
- The PostgreSQL container is started exactly once per pytest session via the
  ``_postgres_container`` session-scoped fixture.
- Each pytest session gets a unique container name, avoiding cross-process
  teardown races when multiple test commands run close together.
- Teardown removes the container by that unique name.  An ``atexit`` handler is
  registered as a fallback for hard crashes that bypass normal pytest teardown.

Schema isolation
-----------------
- ``db_engine`` is session-scoped: tables are created once and dropped once,
  avoiding the overhead of schema recreation on every test.
- ``db_session`` yields a session bound to the engine; ``_truncate_tables``
  (autouse) handles cleanup after each test.
- ``db_factory`` returns independent sessions that commit real data.  The
  ``_truncate_tables`` autouse fixture truncates all user tables after every
  test that requests ``db_factory`` or ``db_session``, keeping tests isolated.
"""

from __future__ import annotations

import atexit
import logging
import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer

from backend.core.database import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants and helpers -- defined first so atexit can reference them.
# ---------------------------------------------------------------------------

_CONTAINER_NAME_PREFIX = "cc-test-postgres"
_container_ref: PostgresContainer | None = None
_container_name: str | None = None


def _force_kill_container(name: str) -> None:
    """Kill and remove a named container via the Docker SDK (SIGKILL, no wait)."""
    try:
        import docker

        client = docker.from_env()
        try:
            c = client.containers.get(name)
            c.kill()
            c.remove(force=True, v=True)
            logger.info("force-killed container %s", name)
        except docker.errors.NotFound:
            pass  # already gone
        finally:
            client.close()
    except Exception as exc:
        logger.warning("error force-killing container %s: %s", name, exc)


def _stop_container_atexit() -> None:
    """Belt-and-suspenders cleanup called on interpreter exit."""
    global _container_ref, _container_name
    if _container_name is not None:
        _force_kill_container(_container_name)
        _container_ref = None
        _container_name = None


atexit.register(_stop_container_atexit)


# ---------------------------------------------------------------------------
# Container fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _postgres_container():
    """Start a named PostgreSQL 17 container for the entire test session.

    The image defaults to the TimescaleDB PostgreSQL image used by the stack,
    and can be overridden with ``CC_TEST_POSTGRES_IMAGE``.
    """
    global _container_ref, _container_name

    _container_name = f"{_CONTAINER_NAME_PREFIX}-{uuid.uuid4().hex[:12]}"
    image = os.environ.get("CC_TEST_POSTGRES_IMAGE", "timescale/timescaledb-ha:pg18")
    container = PostgresContainer(image).with_name(_container_name)
    try:
        container.start()
        _container_ref = container
        logger.info("postgres testcontainer started: %s", container.get_container_host_ip())
        yield container
    finally:
        if _container_name is not None:
            _force_kill_container(_container_name)
        _container_ref = None
        _container_name = None


@pytest.fixture(scope="session", autouse=True)
def _ensure_container_started(_postgres_container):
    """Force the container to start before any test in the session runs.

    ``autouse=True`` + ``scope="session"`` causes pytest to resolve this
    fixture (and therefore ``_postgres_container``) before any test runs.
    """


@pytest.fixture(scope="session")
def postgres_url(_postgres_container):
    """psycopg3-compatible connection URL for the running container."""
    base_url = _postgres_container.get_connection_url()
    # testcontainers defaults to psycopg2 dialect; swap to psycopg (v3)
    return base_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)


# ---------------------------------------------------------------------------
# Engine / session fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def db_engine(postgres_url):
    """Session-scoped SQLAlchemy engine with the full ORM schema.

    Tables are created once at the start of the session and dropped once at
    the end.  The ``DROP SCHEMA … CASCADE`` teardown handles the circular FK
    between ``event_logs`` and ``workflow_executions``.
    """
    import backend.models  # noqa: F401 -- registers all ORM models with Base

    engine = create_engine(
        postgres_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

    # Ensure pgvector + pgvectorscale are available
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE"))
        conn.commit()

    Base.metadata.create_all(bind=engine)
    yield engine

    try:
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.commit()
    except Exception as exc:
        logger.warning("error dropping test schema: %s", exc)
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def _truncate_tables(request, db_engine):
    """Truncate all user tables after each test that touches the database.

    Only runs when the test requested ``db_session`` or ``db_factory``.
    ``TRUNCATE … RESTART IDENTITY CASCADE`` resets sequences and clears
    FK-linked rows without recreating the schema.
    """
    yield  # let the test run first

    db_fixtures = {"db_session", "db_factory"}
    if not db_fixtures.intersection(request.fixturenames):
        return

    try:
        table_names = inspect(db_engine).get_table_names(schema="public")
        if not table_names:
            return
        quoted = ", ".join(f'"{t}"' for t in table_names)
        with db_engine.connect() as conn:
            # Cap how long TRUNCATE waits for locks.  If a test leaks an open
            # transaction the fixture would otherwise hang indefinitely.
            conn.execute(text("SET lock_timeout = '10s'"))
            conn.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
            conn.commit()
    except Exception as exc:
        logger.warning("error truncating tables after test %s: %s", request.node.nodeid, exc)


@pytest.fixture
def db_session(db_engine):
    """Per-test DB session.

    Yields a session bound to the engine.  ``_truncate_tables`` (autouse)
    handles data cleanup after the test completes.
    """
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session: Session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def db_factory(db_engine):
    """Session factory returning independent sessions bound to the test engine.

    Each call creates a new ``Session``.  Callers are responsible for
    committing and closing their own sessions.  ``_truncate_tables`` (autouse)
    cleans up all committed data after the test.
    """
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    def _make() -> Session:
        return factory()

    return _make
