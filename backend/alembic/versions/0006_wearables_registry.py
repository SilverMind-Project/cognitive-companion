"""Add wearable_devices, wearable_bindings, and rf_nodes tables.

Enforces non-overlapping binding intervals per device via a Postgres GiST
exclusion constraint (``btree_gist``), stores RF node positions in normalized
floor-plan coordinates with ``DOUBLE PRECISION`` floats, and adds optional FiRa
UWB session parameters on UWB ranging anchors.

Revision ID: 0006_wearables_registry
Revises: 0005_cts_camera_ir_capable
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_wearables_registry"
down_revision: str | Sequence[str] | None = "0005_cts_camera_ir_capable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "wearable_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tag_id", sa.Text(), nullable=False, unique=True),
        sa.Column("device_kind", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("adapter_id", sa.Text(), nullable=False),
        sa.Column("hardware_key", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("last_heard_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_battery_fraction", sa.Double(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "device_kind IN ('ble_beacon', 'watch', 'uwb_tag')",
            name="ck_wearable_devices_kind",
        ),
        sa.CheckConstraint(
            "last_battery_fraction IS NULL OR "
            "(last_battery_fraction >= 0.0 AND last_battery_fraction <= 1.0)",
            name="ck_wearable_devices_battery_fraction",
        ),
        sa.UniqueConstraint(
            "adapter_id",
            "hardware_key",
            name="uq_wearable_devices_adapter_hardware_key",
        ),
    )
    op.create_index("ix_wearable_devices_tag_id", "wearable_devices", ["tag_id"], unique=True)
    op.create_index("ix_wearable_devices_adapter_id", "wearable_devices", ["adapter_id"])

    op.create_table(
        "wearable_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wearable_devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            sa.String(length=64),
            sa.ForeignKey("household_members.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_recorded_by", sa.Text(), nullable=False),
        sa.Column(
            "consent_recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_wearable_bindings_valid_range",
        ),
        sa.CheckConstraint(
            "valid_to IS NOT NULL OR member_id IS NOT NULL",
            name="ck_wearable_bindings_active_has_member",
        ),
        postgresql.ExcludeConstraint(
            ("device_id", "="),
            (
                sa.text("tstzrange(valid_from, COALESCE(valid_to, 'infinity'::timestamptz), '[)')"),
                "&&",
            ),
            name="excl_wearable_bindings_no_overlap",
            using="gist",
        ),
    )
    op.create_index("ix_wearable_bindings_device_id", "wearable_bindings", ["device_id"])
    op.create_index("ix_wearable_bindings_member_id", "wearable_bindings", ["member_id"])

    op.create_table(
        "rf_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("anchor_id", sa.Text(), nullable=False, unique=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("adapter_id", sa.Text(), nullable=False),
        sa.Column("node_role", sa.Text(), nullable=False),
        sa.Column("technology", sa.Text(), nullable=False),
        sa.Column(
            "room_id",
            sa.Integer(),
            sa.ForeignKey("rooms.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("x_norm", sa.Double(), nullable=False),
        sa.Column("y_norm", sa.Double(), nullable=False),
        sa.Column("z_m", sa.Double(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("placement_residual_m", sa.Double(), nullable=True),
        sa.Column("uwb_address_hex", sa.String(length=8), nullable=True),
        sa.Column("uwb_channel", sa.Integer(), nullable=True),
        sa.Column("uwb_preamble_index", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "node_role IN ('receiver', 'ranging_anchor')",
            name="ck_rf_nodes_role",
        ),
        sa.CheckConstraint(
            "technology IN ('ble_rssi', 'ble_channel_sounding', 'uwb')",
            name="ck_rf_nodes_technology",
        ),
        sa.CheckConstraint("x_norm >= 0.0 AND x_norm <= 1.0", name="ck_rf_nodes_x_norm"),
        sa.CheckConstraint("y_norm >= 0.0 AND y_norm <= 1.0", name="ck_rf_nodes_y_norm"),
        sa.CheckConstraint("z_m >= 0.0 AND z_m <= 4.0", name="ck_rf_nodes_z_m"),
        sa.CheckConstraint(
            "placement_residual_m IS NULL OR placement_residual_m >= 0.0",
            name="ck_rf_nodes_placement_residual",
        ),
        sa.CheckConstraint(
            "uwb_address_hex IS NULL OR uwb_address_hex ~ '^[0-9a-fA-F]{2}:[0-9a-fA-F]{2}$'",
            name="ck_rf_nodes_uwb_address_hex",
        ),
        sa.CheckConstraint(
            "uwb_channel IS NULL OR uwb_channel IN (5, 9)",
            name="ck_rf_nodes_uwb_channel",
        ),
        sa.CheckConstraint(
            "uwb_preamble_index IS NULL OR (uwb_preamble_index >= 9 AND uwb_preamble_index <= 32)",
            name="ck_rf_nodes_uwb_preamble_index",
        ),
    )
    op.create_index("ix_rf_nodes_anchor_id", "rf_nodes", ["anchor_id"], unique=True)
    op.create_index("ix_rf_nodes_adapter_id", "rf_nodes", ["adapter_id"])
    op.create_index("ix_rf_nodes_room_id", "rf_nodes", ["room_id"])
    op.create_index(
        "uix_rf_nodes_active_uwb_address",
        "rf_nodes",
        [sa.text("lower(uwb_address_hex)")],
        unique=True,
        postgresql_where=sa.text(
            "is_active = true AND technology = 'uwb' AND uwb_address_hex IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uix_rf_nodes_active_uwb_address", table_name="rf_nodes")
    op.drop_index("ix_rf_nodes_room_id", table_name="rf_nodes")
    op.drop_index("ix_rf_nodes_adapter_id", table_name="rf_nodes")
    op.drop_index("ix_rf_nodes_anchor_id", table_name="rf_nodes")
    op.drop_table("rf_nodes")

    op.drop_index("ix_wearable_bindings_member_id", table_name="wearable_bindings")
    op.drop_index("ix_wearable_bindings_device_id", table_name="wearable_bindings")
    op.drop_table("wearable_bindings")

    op.drop_index("ix_wearable_devices_adapter_id", table_name="wearable_devices")
    op.drop_index("ix_wearable_devices_tag_id", table_name="wearable_devices")
    op.drop_table("wearable_devices")
