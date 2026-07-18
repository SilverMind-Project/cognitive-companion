"""Add a one-live-session-per-person unique partial index on guided_sessions.

Closes G19: get_live_session_for_person was a read-then-write check, so a
rule trigger racing a caregiver test-run could double-create live sessions
for the same person. The database now rejects the second insert; the store
maps the resulting IntegrityError onto the same ConflictError the read-check
already raised, so the service-level contract is unchanged.

Revision ID: 0015_guided_live_unique
Revises: 0014_guided_conv_linkage
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_guided_live_unique"
down_revision: str | Sequence[str] | None = "0014_guided_conv_linkage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_guided_sessions_one_live_per_person",
        "guided_sessions",
        ["person_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending', 'active', 'waiting', 'summoning', 'escalated',"
            " 'caregiver_takeover')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_guided_sessions_one_live_per_person", table_name="guided_sessions")
