"""Add floor_region_polygon, floor_region_source, floor_region_set_at to cts_cameras.

Revision ID: 0011_floor_region
Revises: 0010_room_zones
Create Date: 2026-06-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from backend.core.time import UTCDateTime

revision: str = "0011_floor_region"
down_revision: str | Sequence[str] | None = "0010_room_zones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cts_cameras",
        sa.Column(
            "floor_region_polygon",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "cts_cameras",
        sa.Column("floor_region_source", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "cts_cameras",
        sa.Column("floor_region_set_at", UTCDateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cts_cameras", "floor_region_set_at")
    op.drop_column("cts_cameras", "floor_region_source")
    op.drop_column("cts_cameras", "floor_region_polygon")
