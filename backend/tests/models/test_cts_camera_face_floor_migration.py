"""The per-camera face floor migration renames the column, keeps values, and bounds them."""

from __future__ import annotations

import importlib

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, MetaData, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.cts_camera import CtsCamera
from backend.models.room import Room

migration = importlib.import_module("backend.alembic.versions.0003_cts_camera_face_raw_similarity")
TABLE = CtsCamera.__tablename__


def _run(connection: Connection, step) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        step()


def _columns(connection: Connection) -> set[str]:
    return {column["name"] for column in inspect(connection).get_columns(TABLE)}


def _checks(connection: Connection) -> set[str | None]:
    return {check["name"] for check in inspect(connection).get_check_constraints(TABLE)}


def _insert(connection: Connection, camera_id: str, value: float) -> None:
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    session.add(
        CtsCamera(
            id=camera_id, name=camera_id, rtsp_url="rtsp://x", face_id_min_raw_similarity=value
        )
    )
    session.commit()


def _floor(connection: Connection, camera_id: str, column: str) -> float | None:
    return connection.execute(
        text(f"SELECT {column} FROM {TABLE} WHERE id = :id"), {"id": camera_id}
    ).scalar_one()


def test_downgrade_and_upgrade_round_trip_the_floor(db_engine) -> None:
    with db_engine.connect() as connection:
        outer = connection.begin()
        try:
            _insert(connection, "cam-kept", 0.55)

            _run(connection, migration.downgrade)
            assert "face_id_min_confidence" in _columns(connection)
            assert "face_id_min_raw_similarity" not in _columns(connection)
            assert migration._CHECK not in _checks(connection)
            assert _floor(connection, "cam-kept", "face_id_min_confidence") == 0.55

            _run(connection, migration.upgrade)
            assert "face_id_min_raw_similarity" in _columns(connection)
            assert "face_id_min_confidence" not in _columns(connection)
            assert migration._CHECK in _checks(connection)
            assert _floor(connection, "cam-kept", "face_id_min_raw_similarity") == 0.55

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
                diff for diff in compare_metadata(context, metadata) if "face_id" in repr(diff)
            ]
            assert diffs == []
        finally:
            outer.rollback()


@pytest.mark.parametrize("value", [-0.1, 1.5])
def test_out_of_range_floor_is_rejected(db_engine, value: float) -> None:
    with db_engine.connect() as connection:
        outer = connection.begin()
        try:
            with pytest.raises(IntegrityError, match=migration._CHECK):
                _insert(connection, "cam-bad", value)
        finally:
            outer.rollback()


def test_it_follows_the_medication_revision() -> None:
    assert migration.down_revision == "0002_medication_schedule"
