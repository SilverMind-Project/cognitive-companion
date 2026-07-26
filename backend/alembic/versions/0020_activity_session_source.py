"""activity_session_source_and_confidence

Adds provenance (``source``) and ``confidence`` to activity_sessions.

``open_session()`` has always accepted a ``confidence`` argument but never
persisted it: the value was dropped on the floor for every caller. DL9 requires
every inferred ledger row to carry both how it was produced and how much to
trust it, so both become real columns here (mirroring ``person_activities``,
which already keeps ``confidence`` on the row).

Existing rows are backfilled with the conservative default ``vision_inferred``
/ ``0.0`` rather than a guessed value: no historical row can prove it came from
a higher-confidence path, and over-claiming confidence on a care record is the
failure mode this column exists to prevent.

Revision ID: 0020_activity_session_source
Revises: 0019_ps_superseded_by_idx
Create Date: 2026-07-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020_activity_session_source"
down_revision: str | Sequence[str] | None = "0019_ps_superseded_by_idx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "activity_sessions",
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="vision_inferred",
        ),
    )
    op.add_column(
        "activity_sessions",
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.create_index(
        "ix_activity_sessions_source",
        "activity_sessions",
        ["source"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_activity_sessions_source", table_name="activity_sessions")
    op.drop_column("activity_sessions", "confidence")
    op.drop_column("activity_sessions", "source")
