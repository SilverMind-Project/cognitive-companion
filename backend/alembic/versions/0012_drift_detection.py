"""Add drift detection columns to cts_cameras.

Columns added:
  - needs_recalibration: bool, default False — set when drift is detected
  - drift_checked_at: timestamptz nullable — last drift check time
  - drift_reason: text nullable — human-readable reason from drift scorer
  - calibration_ref_key: text nullable — MinIO key of the reference frame
      captured at the time of the last committed calibration

Revision ID: 0012_drift_detection
Revises: 0011_floor_region
Create Date: 2026-06-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from backend.core.time import UTCDateTime

revision: str = "0012_drift_detection"
down_revision: str | Sequence[str] | None = "0011_floor_region"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cts_cameras",
        sa.Column(
            "needs_recalibration",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "cts_cameras",
        sa.Column("drift_checked_at", UTCDateTime(), nullable=True),
    )
    op.add_column(
        "cts_cameras",
        sa.Column("drift_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "cts_cameras",
        sa.Column("calibration_ref_key", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cts_cameras", "calibration_ref_key")
    op.drop_column("cts_cameras", "drift_reason")
    op.drop_column("cts_cameras", "drift_checked_at")
    op.drop_column("cts_cameras", "needs_recalibration")
