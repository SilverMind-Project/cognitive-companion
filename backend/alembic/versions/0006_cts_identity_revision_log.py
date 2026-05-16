"""Add cts_identity_revision_log table for first-class identity decision audit.

Revision ID: 0006
Revises: 0005_expand_version_num
Create Date: 2026-05-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_cts_identity_revision_log"
down_revision: str | None = "0005_expand_version_num"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cts_identity_revision_log",
        sa.Column("revision_id", sa.String(128), primary_key=True),
        sa.Column("global_track_id", sa.String(128), nullable=False),
        sa.Column("previous_identity_id", sa.String(128), nullable=True),
        sa.Column("new_identity_id", sa.String(128), nullable=True),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(512), nullable=True),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("rewritten_rows", sa.Integer(), default=0),
        sa.Column("evidence", postgresql.JSONB, nullable=True),
    )
    op.create_index(
        "ix_cts_identity_revision_log_applied_at",
        "cts_identity_revision_log",
        [sa.text("applied_at DESC")],
    )
    op.create_index(
        "ix_cts_identity_revision_log_gt_applied",
        "cts_identity_revision_log",
        ["global_track_id", sa.text("applied_at DESC")],
    )
    op.create_index(
        "ix_cts_identity_revision_log_kind_applied",
        "cts_identity_revision_log",
        ["kind", sa.text("applied_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("cts_identity_revision_log")
