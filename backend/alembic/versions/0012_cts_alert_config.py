"""Add cts_alert_config JSON column to household_members.

Revision ID: 0012_cts_alert_config
Revises: 0011_cts_adjacency_edges
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0012_cts_alert_config"
down_revision: str | None = "0011_cts_adjacency_edges"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "household_members",
        sa.Column("cts_alert_config", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("household_members", "cts_alert_config")
