"""Add household_settings singleton and rooms.floor_polygon.

Revision ID: 0010
Revises: 0009_alert_suppressions_and_priority
Create Date: 2026-05-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_floor_plan_and_room_polygons"
down_revision: str | None = "0009_alert_suppressions_and_priority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "household_settings",
        sa.Column("id", sa.Integer(), primary_key=True, server_default="1"),
        sa.Column("floor_plan_key", sa.String(512), nullable=True),
        sa.Column("floor_plan_width", sa.Integer(), nullable=True),
        sa.Column("floor_plan_height", sa.Integer(), nullable=True),
        sa.Column("floor_meters_per_pixel", sa.Float(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_household_settings_singleton"),
    )

    op.add_column(
        "rooms",
        sa.Column("floor_polygon", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rooms", "floor_polygon")
    op.drop_table("household_settings")
