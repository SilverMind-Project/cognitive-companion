"""Add rotation_degrees column to cts_cameras.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cts_cameras",
        sa.Column("rotation_degrees", sa.Integer(), nullable=False, server_default="0"),
    )
    # Enforce only valid rotation values at the database level.
    op.create_check_constraint(
        "ck_cts_cameras_rotation",
        "cts_cameras",
        "rotation_degrees IN (0, 90, 180, 270)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_cts_cameras_rotation", "cts_cameras", type_="check")
    op.drop_column("cts_cameras", "rotation_degrees")
