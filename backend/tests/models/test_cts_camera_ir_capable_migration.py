"""The ir_capable camera migration adds the nullable boolean column and reverses cleanly."""

from __future__ import annotations

import importlib

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, MetaData, inspect, text
from sqlalchemy.orm import Session

from backend.models.cts_camera import CtsCamera
from backend.models.room import Room

migration = importlib.import_module("backend.alembic.versions.0005_cts_camera_ir_capable")
TABLE = CtsCamera.__tablename__


def _run(connection: Connection, step) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        step()


def _columns(connection: Connection) -> set[str]:
    return {column["name"] for column in inspect(connection).get_columns(TABLE)}


def test_downgrade_and_upgrade_round_trip_ir_capable(db_engine) -> None:
    with db_engine.connect() as connection:
        outer = connection.begin()
        try:
            session = Session(bind=connection, join_transaction_mode="create_savepoint")
            session.add(
                CtsCamera(
                    id="cam-ir",
                    name="Hallway ID",
                    rtsp_url="rtsp://x",
                    role="face_capable",
                    face_id_enabled=False,
                    ir_capable=True,
                )
            )
            session.commit()

            assert "ir_capable" in _columns(connection)
            assert (
                connection.execute(
                    text(f"SELECT ir_capable FROM {TABLE} WHERE id = 'cam-ir'")
                ).scalar_one()
                is True
            )

            _run(connection, migration.downgrade)
            assert "ir_capable" not in _columns(connection)
            # Existing face_id_enabled and role columns remain intact.
            assert "face_id_enabled" in _columns(connection)
            assert "role" in _columns(connection)

            _run(connection, migration.upgrade)
            assert "ir_capable" in _columns(connection)
            assert (
                connection.execute(
                    text(f"SELECT ir_capable FROM {TABLE} WHERE id = 'cam-ir'")
                ).scalar_one()
                is None
            )

            metadata = MetaData()
            Room.__table__.to_metadata(metadata)
            CtsCamera.__table__.to_metadata(metadata)
            context = MigrationContext.configure(
                connection,
                opts={
                    "compare_type": True,
                    "include_object": lambda _object, name, kind, _reflected, _compare: (
                        kind != "table" or name == TABLE
                    ),
                },
            )
            diffs = [
                diff for diff in compare_metadata(context, metadata) if "ir_capable" in repr(diff)
            ]
            assert diffs == []
        finally:
            outer.rollback()


def test_it_follows_drop_cts_adjacency_edges() -> None:
    assert migration.down_revision == "0004_drop_cts_adjacency_edges"
