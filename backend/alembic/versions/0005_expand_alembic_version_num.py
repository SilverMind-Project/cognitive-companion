"""Expand alembic_version.version_num to VARCHAR(64) to support longer revision IDs.

Revision ID: 0005
Revises: 0004_cts_signal_id_algo_version
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_expand_version_num"
down_revision: str | None = "0004_cts_signal_id_algo_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(64),
        existing_type=sa.String(32),
    )


def downgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(32),
        existing_type=sa.String(64),
    )
