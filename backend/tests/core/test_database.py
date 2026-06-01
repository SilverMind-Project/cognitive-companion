"""Tests for :mod:`backend.core.database`."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core import database as db_module
from backend.core.database import (
    Base,
    Database,
    get_db,
    get_session,
    init_db,
    reset_default_database,
)


class _Widget(Base):
    """Throwaway ORM model used by these tests only.

    Lives under the shared ``Base`` so ``Base.metadata.create_all`` will pick
    it up, but it's defined inside the test module to avoid polluting
    ``backend.models``.
    """

    __tablename__ = "_test_widgets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()


@pytest.fixture
def test_db(postgres_url: str) -> Database:
    """PostgreSQL Database with the _Widget table created."""
    d = Database(postgres_url)
    Base.metadata.create_all(bind=d.engine, tables=[_Widget.__table__])
    yield d
    with d.engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "_test_widgets"'))
    d.dispose()


class TestDatabaseClass:
    def test_engine_and_url(self, test_db: Database, postgres_url: str) -> None:
        assert test_db.url == postgres_url
        assert test_db.engine is not None

    def test_session_returns_new_session_each_call(self, test_db: Database) -> None:
        s1 = test_db.session()
        s2 = test_db.session()
        assert s1 is not s2
        s1.close()
        s2.close()

    def test_session_can_insert_and_query(self, test_db: Database) -> None:
        sess = test_db.session()
        sess.add(_Widget(name="alpha"))
        sess.commit()
        rows = sess.execute(text("SELECT name FROM _test_widgets")).fetchall()
        assert rows == [("alpha",)]
        sess.close()

    def test_session_scope_closes_on_exit(self, test_db: Database) -> None:
        gen = test_db.session_scope()
        sess = next(gen)
        sess.add(_Widget(name="beta"))
        sess.commit()
        with pytest.raises(StopIteration):
            next(gen)

    def test_dispose_is_idempotent(self, test_db: Database) -> None:
        test_db.dispose()
        test_db.dispose()  # second call must not raise


class TestPostgreSQLDialect:
    def test_postgresql_engine_dialect(self) -> None:
        """PostgreSQL enforces foreign keys by default; no pragma needed."""
        d = Database("postgresql+psycopg://user:pass@localhost/db")
        try:
            assert d.engine.dialect.name == "postgresql"
        finally:
            d.dispose()


class TestResolveUrl:
    def test_raises_when_url_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_resolve_url raises RuntimeError when database.url is absent."""
        from backend.core.config import Settings

        monkeypatch.setattr(db_module, "settings", Settings.from_dict({}))
        with pytest.raises(RuntimeError, match=r"database\.url is not configured"):
            db_module._resolve_url(None)


class TestModuleFacade:
    def test_reset_clears_cached_default(self, postgres_url: str) -> None:
        db_module._default_database = Database(postgres_url)
        reset_default_database()
        assert db_module._default_database is None

    def test_get_session_creates_default_on_demand(
        self, monkeypatch: pytest.MonkeyPatch, postgres_url: str
    ) -> None:
        reset_default_database()
        monkeypatch.setattr(
            db_module,
            "_resolve_url",
            lambda _url=None: postgres_url,
        )
        sess = get_session()
        assert sess is not None
        sess.close()
        reset_default_database()

    def test_get_db_yields_then_closes(
        self, monkeypatch: pytest.MonkeyPatch, postgres_url: str
    ) -> None:
        reset_default_database()
        monkeypatch.setattr(
            db_module,
            "_resolve_url",
            lambda _url=None: postgres_url,
        )
        gen = get_db()
        sess = next(gen)
        assert sess is not None
        with pytest.raises(StopIteration):
            next(gen)
        reset_default_database()

    def test_init_db_with_explicit_url_replaces_default(self, postgres_url: str) -> None:
        reset_default_database()

        init_db(postgres_url, run_migrations=False)
        try:
            assert db_module._default_database is not None
            assert db_module._default_database.url == postgres_url
        finally:
            reset_default_database()
