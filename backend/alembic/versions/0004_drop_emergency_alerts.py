"""Drop the dead emergency_alerts table.

No writer ever inserted into ``emergency_alerts``; caregiver alerts now flow
through the unified signals feed (CTS dementia signals + pipeline-rule
notifications). See PRESENCE_SURFACE_AUDIT.md.

Revision ID: 0004_drop_emergency_alerts
Revises: 0003_drop_branch_columns
Create Date: 2026-06-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

import backend.core.time
from alembic import op

revision: str = "0004_drop_emergency_alerts"
down_revision: str | Sequence[str] | None = "0003_drop_branch_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("emergency_alerts")


def downgrade() -> None:
    op.create_table(
        "emergency_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "timestamp",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sensor_id", sa.String(length=128), nullable=True),
        sa.Column("room_name", sa.String(length=128), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("assistance_needed", sa.Boolean(), nullable=False),
        sa.Column("notification_sent_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
