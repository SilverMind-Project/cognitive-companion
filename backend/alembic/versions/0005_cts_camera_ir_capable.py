"""Add optional ir_capable capability flag to cts_cameras.

Cameras with infrared illumination switch to grayscale at night, which changes face and
body appearance distributions. Storing this declared capability alongside FOV, mounting
height, tilt, and role lets operators set expectations without naming a vendor or model.

Revision ID: 0005_cts_camera_ir_capable
Revises: 0004_drop_cts_adjacency_edges
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_cts_camera_ir_capable"
down_revision: str | Sequence[str] | None = "0004_drop_cts_adjacency_edges"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cts_cameras", sa.Column("ir_capable", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("cts_cameras", "ir_capable")
