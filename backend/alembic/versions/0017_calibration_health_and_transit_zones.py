"""Add calibration health columns to cts_cameras, has_camera to rooms,
and create transit_zones table.

Revision ID: 0017_calibration_health_and_transit_zones
Revises: 0016_cts_camera_visibility
Create Date: 2026-05-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0017_calibration_health_and_transit_zones"
down_revision: str | None = "0016_cts_camera_visibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- cts_cameras: calibration health columns ---
    # NOTE: room_id was already added in migration 0007_cts_camera_room_linkage,
    # which also created index ix_cts_cameras_room_id but no FK constraint. We
    # add the FK here.
    op.add_column("cts_cameras", sa.Column("homography_matrix", JSONB, nullable=True))
    op.add_column("cts_cameras", sa.Column("homography_residual_m", sa.Float(), nullable=True))
    op.add_column(
        "cts_cameras",
        sa.Column("homography_method", sa.String(32), nullable=True),
    )
    op.add_column(
        "cts_cameras", sa.Column("homography_set_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "cts_cameras", sa.Column("frame_natural_width", sa.Integer(), nullable=True)
    )
    op.add_column(
        "cts_cameras", sa.Column("frame_natural_height", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_cts_cameras_room_id", "cts_cameras", "rooms", ["room_id"], ["id"]
    )

    # --- rooms: camera-blind room support ---
    op.add_column(
        "rooms",
        sa.Column("has_camera", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
    )
    op.add_column(
        "rooms",
        sa.Column("inferred_dwell_alert_minutes", sa.Integer(), nullable=True),
    )

    # --- transit_zones ---
    op.create_table(
        "transit_zones",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column(
            "kind",
            sa.String(32),
            nullable=False,
            server_default="door",
        ),
        sa.Column("polygon", JSONB, nullable=False),
        sa.Column("inside_room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("outside_room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("direction_vec", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("transit_zones")
    op.drop_column("rooms", "inferred_dwell_alert_minutes")
    op.drop_column("rooms", "has_camera")
    op.drop_constraint("fk_cts_cameras_room_id", "cts_cameras")
    op.drop_column("cts_cameras", "frame_natural_height")
    op.drop_column("cts_cameras", "frame_natural_width")
    op.drop_column("cts_cameras", "homography_set_at")
    op.drop_column("cts_cameras", "homography_method")
    op.drop_column("cts_cameras", "homography_residual_m")
    op.drop_column("cts_cameras", "homography_matrix")
    # room_id is NOT dropped here; it is owned by migration 0007.
