"""Add cts_window_triggers and rule_cts_window_triggers join table.

Revision ID: 0002
Revises: 0001_initial_schema
Create Date: 2026-05-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cts_window_triggers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("window_seconds", sa.Float(), nullable=False, server_default="10.0"),
        sa.Column("min_detections", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("min_identities", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cameras", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("rooms", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("cooldown_seconds", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "rule_cts_window_triggers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "rule_id", sa.Integer(), sa.ForeignKey("rules.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "cts_window_trigger_id",
            sa.String(36),
            sa.ForeignKey("cts_window_triggers.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_rule_cts_window_triggers_rule_id",
        "rule_cts_window_triggers",
        ["rule_id"],
    )
    op.create_index(
        "ix_rule_cts_window_triggers_ct_id",
        "rule_cts_window_triggers",
        ["cts_window_trigger_id"],
    )


def downgrade() -> None:
    op.drop_table("rule_cts_window_triggers")
    op.drop_table("cts_window_triggers")
