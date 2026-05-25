"""Add visibility_polygon column to cts_cameras.

Revision ID: 0016_cts_camera_visibility
Revises: 0015_cts_camera_physical
Create Date: 2026-05-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0016_cts_camera_visibility"
down_revision: str | None = "0015_cts_camera_physical"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cts_cameras", sa.Column("visibility_polygon", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("cts_cameras", "visibility_polygon")
