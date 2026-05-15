"""Add signal_id and algorithm_version columns to cts_dementia_signals.

Revision ID: 0004
Revises: 990462f4cf44
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_cts_signal_id_algo_version"
down_revision: str | None = "990462f4cf44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cts_dementia_signals",
        sa.Column("signal_id", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_cts_dementia_signals_signal_id",
        "cts_dementia_signals",
        ["signal_id"],
    )
    op.add_column(
        "cts_dementia_signals",
        sa.Column("algorithm_version", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cts_dementia_signals", "algorithm_version")
    op.drop_index("ix_cts_dementia_signals_signal_id")
    op.drop_column("cts_dementia_signals", "signal_id")
