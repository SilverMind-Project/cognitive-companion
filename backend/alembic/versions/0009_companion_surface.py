"""Add companion surface registry.

Revision ID: 0009_companion_surface
Revises: 0008_guided_task
Create Date: 2026-06-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from backend.core.time import UTCDateTime

revision: str = "0009_companion_surface"
down_revision: str | Sequence[str] | None = "0008_guided_task"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companion_surfaces",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("surface_type", sa.String(length=16), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("room_source", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", UTCDateTime(), nullable=True),
        sa.Column("room_mismatch", sa.Boolean(), nullable=False),
        sa.Column("created_at", UTCDateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", UTCDateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_companion_surfaces_room_id"),
        "companion_surfaces",
        ["room_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_companion_surfaces_room_id"), table_name="companion_surfaces")
    op.drop_table("companion_surfaces")
