"""Tests for :mod:`backend.core.database`."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core import database as db_module
from backend.core.database import (
    Base,
    Database,
    _apply_column_migrations,
    get_db,
    get_session,
    init_db,
    reset_default_database,
)


class _Widget(Base):
    """Throwaway ORM model used by these tests only.

    Lives under the shared ``Base`` so ``Base.metadata.create_all`` will pick
    it up in the in-memory DB, but it's defined inside the test module to
    avoid polluting ``backend.models``.
    """

    __tablename__ = "_test_widgets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()


@pytest.fixture
def mem_db() -> Database:
    """In-memory Database with the _Widget table created."""
    d = Database("sqlite:///:memory:")
    Base.metadata.create_all(bind=d.engine, tables=[_Widget.__table__])
    yield d
    d.dispose()


class TestDatabaseClass:
    def test_engine_and_url(self, mem_db: Database) -> None:
        assert mem_db.url == "sqlite:///:memory:"
        assert mem_db.engine is not None

    def test_session_returns_new_session_each_call(self, mem_db: Database) -> None:
        s1 = mem_db.session()
        s2 = mem_db.session()
        assert s1 is not s2
        s1.close()
        s2.close()

    def test_session_can_insert_and_query(self, mem_db: Database) -> None:
        sess = mem_db.session()
        sess.add(_Widget(name="alpha"))
        sess.commit()
        rows = sess.execute(text("SELECT name FROM _test_widgets")).fetchall()
        assert rows == [("alpha",)]
        sess.close()

    def test_session_scope_closes_on_exit(self, mem_db: Database) -> None:
        gen = mem_db.session_scope()
        sess = next(gen)
        sess.add(_Widget(name="beta"))
        sess.commit()
        # Exhaust the generator to trigger cleanup.
        with pytest.raises(StopIteration):
            next(gen)

    def test_dispose_is_idempotent(self, mem_db: Database) -> None:
        mem_db.dispose()
        mem_db.dispose()  # second call must not raise


class TestSqlitePragmas:
    def test_foreign_keys_enabled_on_sqlite(self) -> None:
        d = Database("sqlite:///:memory:")
        try:
            with d.engine.connect() as conn:
                val = conn.execute(text("PRAGMA foreign_keys")).scalar()
                assert val == 1
        finally:
            d.dispose()

    def test_journal_mode_is_wal_like(self) -> None:
        # WAL isn't supported on :memory: DBs (it falls back to 'memory'),
        # but the PRAGMA call must not raise and must return *some* value.
        d = Database("sqlite:///:memory:")
        try:
            with d.engine.connect() as conn:
                mode = conn.execute(text("PRAGMA journal_mode")).scalar()
                assert mode is not None
        finally:
            d.dispose()

    def test_parent_dir_created_for_file_sqlite(self, tmp_path: Path) -> None:
        nested = tmp_path / "nested" / "deeper" / "test.db"
        assert not nested.parent.exists()
        d = Database(f"sqlite:///{nested}")
        try:
            assert nested.parent.exists()
        finally:
            d.dispose()


class TestApplyColumnMigrations:
    """``_apply_column_migrations`` adds nullable columns to existing tables."""

    def test_idempotent_when_columns_already_exist(self) -> None:
        """Running migrations on a schema that already has all columns must not raise."""
        import backend.models  # noqa: F401 -- registers ActiveImageState with Base

        d = Database("sqlite:///:memory:")
        try:
            Base.metadata.create_all(bind=d.engine)
            # Columns were created by create_all; second call must succeed silently.
            _apply_column_migrations(d.engine)
        finally:
            d.dispose()

    def test_adds_missing_columns(self, tmp_path: Path) -> None:
        """Columns absent from an older schema are added by the migration."""
        db_path = tmp_path / "old_schema.db"
        d = Database(f"sqlite:///{db_path}")
        try:
            # Create a minimal active_image_state table without the new columns,
            # simulating a database that pre-dates the refresh-suppression feature.
            with d.engine.connect() as conn:
                conn.execute(
                    text(
                        "CREATE TABLE active_image_state ("
                        "  id INTEGER PRIMARY KEY,"
                        "  sensor_id VARCHAR(128) UNIQUE"
                        ")"
                    )
                )
                conn.commit()

            _apply_column_migrations(d.engine)

            with d.engine.connect() as conn:
                col_names = {
                    row[1] for row in conn.execute(text("PRAGMA table_info(active_image_state)"))
                }

            assert "last_served_hash" in col_names
            assert "last_served_at" in col_names
        finally:
            d.dispose()

    def test_skips_gracefully_when_table_absent(self) -> None:
        """OperationalError from a missing table is caught; no exception propagates."""
        d = Database("sqlite:///:memory:")
        try:
            # No tables created -- the migration statements will hit
            # "no such table: active_image_state", which is an OperationalError.
            _apply_column_migrations(d.engine)
        finally:
            d.dispose()


class TestModuleFacade:
    def test_reset_clears_cached_default(self) -> None:
        db_module._default_database = Database("sqlite:///:memory:")
        reset_default_database()
        assert db_module._default_database is None

    def test_get_session_creates_default_on_demand(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reset_default_database()
        monkeypatch.setattr(
            db_module,
            "_resolve_url",
            lambda _url=None: "sqlite:///:memory:",
        )
        sess = get_session()
        assert sess is not None
        sess.close()
        reset_default_database()

    def test_get_db_yields_then_closes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reset_default_database()
        monkeypatch.setattr(
            db_module,
            "_resolve_url",
            lambda _url=None: "sqlite:///:memory:",
        )
        gen = get_db()
        sess = next(gen)
        assert sess is not None
        # Exhaust generator to run `finally` branch.
        with pytest.raises(StopIteration):
            next(gen)
        reset_default_database()

    def test_init_db_with_explicit_url_replaces_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reset_default_database()
        # Ensure init_db can do a full create_all() — stub out backend.models
        # so the import inside Database.create_all() is a no-op rather than
        # dragging in the full ORM for this micro-test.
        import sys
        import types

        monkeypatch.setitem(sys.modules, "backend.models", types.ModuleType("backend.models"))

        db_path = tmp_path / "explicit.db"
        init_db(f"sqlite:///{db_path}")
        try:
            assert db_module._default_database is not None
            assert db_module._default_database.url == f"sqlite:///{db_path}"
        finally:
            reset_default_database()
