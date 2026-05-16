"""Add alert suppressions and alert_priority to household_members.

Revision ID: 0009
Revises: 0008_cts_camera_role_and_overlap
Create Date: 2026-05-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_alert_suppressions_and_priority"
down_revision: str | None = "0008_cts_camera_role_and_overlap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cts_alert_suppressions",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            "person_id",
            sa.String(64),
            sa.ForeignKey("household_members.id"),
            nullable=False,
        ),
        sa.Column("signal_kind", sa.String(64), nullable=True),
        sa.Column(
            "suppressed_until",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_alert_suppressions_person_until",
        "cts_alert_suppressions",
        ["person_id", "suppressed_until"],
    )

    op.add_column(
        "household_members",
        sa.Column(
            "alert_priority",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
    )


def downgrade() -> None:
    op.drop_column("household_members", "alert_priority")
    op.drop_table("cts_alert_suppressions")
