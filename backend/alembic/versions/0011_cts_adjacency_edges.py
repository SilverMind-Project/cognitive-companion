"""Add cts_adjacency_edges JSON column to household_settings.

Revision ID: 0011_cts_adjacency_edges
Revises: 0010_floor_plan_and_room_polygons
Create Date: 2026-05-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_cts_adjacency_edges"
down_revision: str | None = "0010_floor_plan_and_room_polygons"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "household_settings",
        sa.Column("cts_adjacency_edges", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("household_settings", "cts_adjacency_edges")
