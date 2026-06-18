"""Add room zones and routine-step zone FK.

M3 intentionally created routine_steps.zone_id as a nullable integer without a
foreign key. This migration creates room_zones and adds that deferred FK.

Revision ID: 0010_room_zones
Revises: 0009_companion_surface
Create Date: 2026-06-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from backend.core.time import UTCDateTime

revision: str = "0010_room_zones"
down_revision: str | Sequence[str] | None = "0009_companion_surface"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "room_zones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=True),
        sa.Column("polygon", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("camera_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("created_at", UTCDateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", UTCDateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "name", name="uq_room_zone_name"),
    )
    op.create_index(op.f("ix_room_zones_room_id"), "room_zones", ["room_id"], unique=False)
    op.create_foreign_key(
        "fk_routine_steps_zone_id_room_zones",
        "routine_steps",
        "room_zones",
        ["zone_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_routine_steps_zone_id_room_zones",
        "routine_steps",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_room_zones_room_id"), table_name="room_zones")
    op.drop_table("room_zones")
