"""Alembic upgrade/downgrade and Postgres constraint tests for 0006_wearables_registry."""

from __future__ import annotations

import importlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.person import HouseholdMember
from backend.models.wearable import RfNode, WearableBinding, WearableDevice

migration = importlib.import_module("backend.alembic.versions.0006_wearables_registry")
migration_0008 = importlib.import_module("backend.alembic.versions.0008_rf_node_firmware_version")


def _run(connection: Connection, step) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        step()


def _tables(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names())


def test_it_follows_cts_camera_ir_capable() -> None:
    assert migration.down_revision == "0005_cts_camera_ir_capable"
    assert migration_0008.down_revision == "0007_household_member_height_cm"


def test_0008_firmware_version_downgrade_and_upgrade_round_trip(db_engine) -> None:
    with db_engine.connect() as connection:
        outer = connection.begin()
        try:
            cols_before = {c["name"] for c in inspect(connection).get_columns("rf_nodes")}
            assert "firmware_version" in cols_before

            _run(connection, migration_0008.downgrade)
            cols_after_down = {c["name"] for c in inspect(connection).get_columns("rf_nodes")}
            assert "firmware_version" not in cols_after_down

            _run(connection, migration_0008.upgrade)
            cols_after_up = {c["name"] for c in inspect(connection).get_columns("rf_nodes")}
            assert "firmware_version" in cols_after_up
        finally:
            outer.rollback()


def test_downgrade_and_upgrade_round_trip_wearables_registry(db_engine) -> None:
    with db_engine.connect() as connection:
        outer = connection.begin()
        try:
            assert {"wearable_devices", "wearable_bindings", "rf_nodes"} <= _tables(connection)

            _run(connection, migration.downgrade)
            tables_after_down = _tables(connection)
            assert "wearable_devices" not in tables_after_down
            assert "wearable_bindings" not in tables_after_down
            assert "rf_nodes" not in tables_after_down

            _run(connection, migration.upgrade)
            assert {"wearable_devices", "wearable_bindings", "rf_nodes"} <= _tables(connection)
            _run(connection, migration_0008.upgrade)

            # Verify DOUBLE PRECISION columns on rf_nodes (not float4/REAL).
            col_types = {
                row[0]: row[1]
                for row in connection.execute(
                    text(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_name = 'rf_nodes' "
                        "AND column_name IN ('x_norm', 'y_norm', 'z_m', 'placement_residual_m')"
                    )
                ).all()
            }
            assert col_types == {
                "x_norm": "double precision",
                "y_norm": "double precision",
                "z_m": "double precision",
                "placement_residual_m": "double precision",
            }

            # Verify GiST exclusion constraint rejects overlapping binding intervals.
            session = Session(bind=connection, join_transaction_mode="create_savepoint")
            member_a = HouseholdMember(id="mig-a", name="Member A")
            member_b = HouseholdMember(id="mig-b", name="Member B")
            device = WearableDevice(
                id=uuid.uuid4(),
                tag_id="mig-tag-1",
                device_kind="ble_beacon",
                label="Wristband",
                adapter_id="ble-home",
                hardware_key="uuid:1:1",
            )
            session.add_all([member_a, member_b, device])
            session.flush()

            t0 = datetime(2026, 11, 19, 8, 0, tzinfo=UTC)
            t1 = t0 + timedelta(hours=2)
            t2 = t1 + timedelta(hours=2)
            session.add(
                WearableBinding(
                    id=uuid.uuid4(),
                    device_id=device.id,
                    member_id=member_a.id,
                    valid_from=t0,
                    valid_to=t1,
                    consent_recorded_by="Caregiver",
                    consent_recorded_at=t0,
                    created_by="Admin",
                )
            )
            session.commit()

            # Adjacent half-open interval [t1, t2) is permitted.
            session.add(
                WearableBinding(
                    id=uuid.uuid4(),
                    device_id=device.id,
                    member_id=member_b.id,
                    valid_from=t1,
                    valid_to=t2,
                    consent_recorded_by="Caregiver",
                    consent_recorded_at=t1,
                    created_by="Admin",
                )
            )
            session.commit()

            # Overlapping interval [t0+1h, t1+1h) must be rejected by the DB constraint.
            session.add(
                WearableBinding(
                    id=uuid.uuid4(),
                    device_id=device.id,
                    member_id=member_a.id,
                    valid_from=t0 + timedelta(hours=1),
                    valid_to=t1 + timedelta(hours=1),
                    consent_recorded_by="Caregiver",
                    consent_recorded_at=t1,
                    created_by="Admin",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

            # Active UWB short addresses must be unique (case-insensitive); inactive allowed.
            n1 = RfNode(
                id=uuid.uuid4(),
                anchor_id="uwb-1",
                label="UWB 1",
                adapter_id="uwb-watch",
                node_role="ranging_anchor",
                technology="uwb",
                x_norm=0.2,
                y_norm=0.3,
                z_m=2.0,
                is_active=True,
                uwb_address_hex="00:0A",
                uwb_channel=9,
                uwb_preamble_index=10,
            )
            session.add(n1)
            session.commit()

            session.add(
                RfNode(
                    id=uuid.uuid4(),
                    anchor_id="uwb-2",
                    label="UWB 2",
                    adapter_id="uwb-watch",
                    node_role="ranging_anchor",
                    technology="uwb",
                    x_norm=0.6,
                    y_norm=0.3,
                    z_m=2.0,
                    is_active=True,
                    uwb_address_hex="00:0a",
                    uwb_channel=9,
                    uwb_preamble_index=10,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
        finally:
            outer.rollback()
