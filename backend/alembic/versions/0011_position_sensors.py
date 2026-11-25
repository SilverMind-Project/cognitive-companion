"""Add the position_sensors registry for device-free radar and LiDAR sensors.

A position sensor reports anonymous floor-plane tracks and never identity. The row
names the room it covers (Cognitive Companion presence), its mounting pose on the
floor plan (rf-ingress transforms sensor-frame reports with it), and its systematic
calibration residual (the floor below which tracking never lets it shrink a person's
position uncertainty). It is served to CTS and rf-ingress through the site-config.

Revision ID: 0011_position_sensors
Revises: 0010_wearable_physical_device_id
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011_position_sensors"
down_revision: str | Sequence[str] | None = "0010_wearable_physical_device_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "position_sensors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("sensor_id", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("modality", sa.Text(), nullable=False),
        sa.Column(
            "room_id",
            sa.Integer(),
            sa.ForeignKey("rooms.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("x_norm", sa.Double(), nullable=False),
        sa.Column("y_norm", sa.Double(), nullable=False),
        sa.Column("yaw_deg", sa.Double(), nullable=True),
        sa.Column(
            "calibration_residual_m",
            sa.Double(),
            nullable=False,
            server_default=sa.text("0.10"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
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
            "sensor_id ~ '^[a-z0-9][a-z0-9_.-]{0,63}$'",
            name="ck_position_sensors_sensor_id",
        ),
        sa.CheckConstraint(
            "modality IN ('mmwave_radar', 'lidar', 'other')",
            name="ck_position_sensors_modality",
        ),
        sa.CheckConstraint("x_norm >= 0.0 AND x_norm <= 1.0", name="ck_position_sensors_x_norm"),
        sa.CheckConstraint("y_norm >= 0.0 AND y_norm <= 1.0", name="ck_position_sensors_y_norm"),
        sa.CheckConstraint(
            "yaw_deg IS NULL OR (yaw_deg >= -180.0 AND yaw_deg < 180.0)",
            name="ck_position_sensors_yaw_deg",
        ),
        sa.CheckConstraint(
            "calibration_residual_m > 0.0 AND calibration_residual_m <= 1.0",
            name="ck_position_sensors_calibration_residual",
        ),
    )
    op.create_index("ix_position_sensors_sensor_id", "position_sensors", ["sensor_id"], unique=True)
    op.create_index("ix_position_sensors_room_id", "position_sensors", ["room_id"])


def downgrade() -> None:
    op.drop_index("ix_position_sensors_room_id", table_name="position_sensors")
    op.drop_index("ix_position_sensors_sensor_id", table_name="position_sensors")
    op.drop_table("position_sensors")
