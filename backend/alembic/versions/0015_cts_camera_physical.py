"""Add physical camera parameters and snapshot dimensions to cts_cameras.

Revision ID: 0015_cts_camera_physical
Revises: 0014_room_occupancy_state
Create Date: 2026-05-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_cts_camera_physical"
down_revision: str | None = "0014_room_occupancy_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cts_cameras", sa.Column("horizontal_fov_deg", sa.Float, nullable=True))
    op.add_column("cts_cameras", sa.Column("mounting_height_m", sa.Float, nullable=True))
    op.add_column("cts_cameras", sa.Column("tilt_deg", sa.Float, nullable=True))
    op.add_column("cts_cameras", sa.Column("snapshot_width", sa.Integer, nullable=True))
    op.add_column("cts_cameras", sa.Column("snapshot_height", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("cts_cameras", "snapshot_height")
    op.drop_column("cts_cameras", "snapshot_width")
    op.drop_column("cts_cameras", "tilt_deg")
    op.drop_column("cts_cameras", "mounting_height_m")
    op.drop_column("cts_cameras", "horizontal_fov_deg")
