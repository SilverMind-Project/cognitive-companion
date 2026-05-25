"""Add camera role and overlap groups for multi-camera composition.

Revision ID: 0008
Revises: 0007_cts_camera_room_linkage
Create Date: 2026-05-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_cts_camera_role_and_overlap"
down_revision: str | None = "0007_cts_camera_room_linkage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cts_cameras",
        sa.Column(
            "role",
            sa.String(32),
            nullable=False,
            server_default="surveillance",
        ),
    )
    # Backfill: cameras with face_id_enabled=True get 'face_capable'
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE cts_cameras SET role = 'face_capable' WHERE face_id_enabled = TRUE"),
    )

    op.create_table(
        "cts_camera_overlap_groups",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("camera_ids", postgresql.ARRAY(sa.String), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("cts_camera_overlap_groups")
    op.drop_column("cts_cameras", "role")
