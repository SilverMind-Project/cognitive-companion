"""presence_segments_superseded_by_index

Revision ID: 0019_ps_superseded_by_idx
Revises: 0018_routine_activity_type
Create Date: 2026-07-22 00:00:00.000000

``presence_segments.superseded_by`` is a self-referencing foreign key
(``ON DELETE NO ACTION``, the implicit default) with no supporting index on
the referencing column. Every ``UPDATE``/``DELETE`` that touches a row's
``id`` makes Postgres check "does any row still point at this id via
``superseded_by``" -- without an index on ``superseded_by``, that check is a
full sequential scan per row.

Incident (Daily Living identity-revision-replay bug, 2026-07-22): a stream
redelivery bug in ``PersonLocationService.apply_identity_revision`` (fixed
separately) caused ~2.5M duplicate rows to accumulate for one person. The
one-time cleanup delete against that table, with no index on
``superseded_by``, ran for 12+ minutes before being cancelled; after adding
this index it completed in seconds. Real-world row counts here are normally
small (a single-household deployment), so this index costs little in
steady state, but it turns any future bulk delete/update on this table from
O(n^2) into O(n log n) and is the structurally correct index for a
self-referencing FK regardless.

Partial (``WHERE superseded_by IS NOT NULL``) to match ``idx_ps_person_open``'s
existing partial-index convention in this table: most rows never get
superseded, so indexing only the ones that do keeps it small.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019_ps_superseded_by_idx"
down_revision: str | Sequence[str] | None = "0018_routine_activity_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "idx_ps_superseded_by",
        "presence_segments",
        ["superseded_by"],
        postgresql_where=sa.text("superseded_by IS NOT NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_ps_superseded_by", table_name="presence_segments")
