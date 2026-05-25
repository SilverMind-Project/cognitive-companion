"""Add room_id to cts_cameras and rename location to room_name.

Revision ID: 0007
Revises: 0006_cts_identity_revision_log
Create Date: 2026-05-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_cts_camera_room_linkage"
down_revision: str | None = "0006_cts_identity_revision_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "cts_cameras",
        "location",
        new_column_name="room_name",
        existing_type=sa.String(256),
    )
    op.add_column(
        "cts_cameras",
        sa.Column("room_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_cts_cameras_room_id",
        "cts_cameras",
        ["room_id"],
    )

    # Backfill: match existing room_name to rooms.name (case-insensitive).
    # Unmatched rows keep room_id = NULL.
    conn = op.get_bind()
    rooms = conn.execute(sa.text("SELECT id, name FROM rooms")).fetchall()
    for room in rooms:
        conn.execute(
            sa.text(
                "UPDATE cts_cameras SET room_id = :room_id "
                "WHERE LOWER(room_name) = LOWER(:room_name) AND room_id IS NULL"
            ),
            {"room_id": room.id, "room_name": room.name},
        )


def downgrade() -> None:
    op.drop_index("ix_cts_cameras_room_id", table_name="cts_cameras")
    op.drop_column("cts_cameras", "room_id")
    op.alter_column(
        "cts_cameras",
        "room_name",
        new_column_name="location",
        existing_type=sa.String(256),
    )
