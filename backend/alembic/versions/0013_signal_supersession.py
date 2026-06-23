"""Add superseded_by_revision_id to cts_dementia_signals (M06).

An operator identity correction supersedes the signal rows under the old identity
within the corrected range and inserts replacement rows under the corrected
identity. The original rows are retained for audit; this column marks them.

Revision ID: 0013_signal_supersession
Revises: 0012_drift_detection
Create Date: 2026-06-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_signal_supersession"
down_revision: str | Sequence[str] | None = "0012_drift_detection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cts_dementia_signals",
        sa.Column("superseded_by_revision_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_cts_dementia_signals_superseded_by_revision_id",
        "cts_dementia_signals",
        ["superseded_by_revision_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cts_dementia_signals_superseded_by_revision_id",
        table_name="cts_dementia_signals",
    )
    op.drop_column("cts_dementia_signals", "superseded_by_revision_id")
