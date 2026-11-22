"""Add nullable operator-recorded firmware_version column to rf_nodes.

Revision ID: 0008_rf_node_firmware_version
Revises: 0007_household_member_height_cm
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_rf_node_firmware_version"
down_revision: str | Sequence[str] | None = "0007_household_member_height_cm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rf_nodes",
        sa.Column("firmware_version", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rf_nodes", "firmware_version")
