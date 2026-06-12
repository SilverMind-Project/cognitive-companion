"""Add feedback and evidence_grade columns to cts_dementia_signals.

Revision ID: 0006_add_signal_feedback_evidence_grade
Revises: 0005_add_location_heatmap
Create Date: 2026-06-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_signal_feedback"
down_revision: str | Sequence[str] | None = "0005_add_location_heatmap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cts_dementia_signals",
        sa.Column("feedback", sa.String(16), nullable=True),
    )
    op.add_column(
        "cts_dementia_signals",
        sa.Column("evidence_grade", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cts_dementia_signals", "evidence_grade")
    op.drop_column("cts_dementia_signals", "feedback")
