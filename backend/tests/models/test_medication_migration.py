"""The medication migration runs for real, and builds what the model describes."""

from __future__ import annotations

import importlib

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import MetaData, inspect

from backend.models.medication import MedicationScheduleEntry
from backend.models.person import HouseholdMember

migration = importlib.import_module("backend.alembic.versions.0002_medication_schedule")
TABLE = MedicationScheduleEntry.__tablename__


def _run(connection, step) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        step()


def _table_exists(connection) -> bool:
    return inspect(connection).has_table(TABLE)


def test_upgrade_matches_the_model_and_downgrade_reverses_it(db_engine) -> None:
    with db_engine.begin() as connection:
        MedicationScheduleEntry.__table__.drop(connection)

        _run(connection, migration.upgrade)
        assert _table_exists(connection)

        metadata = MetaData()
        HouseholdMember.__table__.to_metadata(metadata)
        MedicationScheduleEntry.__table__.to_metadata(metadata)
        context = MigrationContext.configure(
            connection,
            opts={
                "compare_type": True,
                "include_object": lambda _object, name, kind, _reflected, _compare: (
                    kind != "table" or name == TABLE
                ),
            },
        )
        assert compare_metadata(context, metadata) == []

        _run(connection, migration.downgrade)
        assert not _table_exists(connection)

        # Leave the schema as the session's other tests expect it.
        _run(connection, migration.upgrade)


def test_it_follows_the_baseline() -> None:
    assert migration.down_revision == "0001_baseline"
