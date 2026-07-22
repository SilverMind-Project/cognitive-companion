"""daily_living_m05_routine_activity_type

Revision ID: 0018_routine_activity_type
Revises: 0017_backfill_segments
Create Date: 2026-07-21 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_routine_activity_type"
down_revision: str | Sequence[str] | None = "0017_backfill_segments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("routines", sa.Column("activity_type", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("routines", "activity_type")
