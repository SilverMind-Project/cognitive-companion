"""Add per-person medication schedules.

Revision ID: 0002_medication_schedule
Revises: 0001_baseline
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_medication_schedule"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "medication_schedule_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "person_id",
            sa.String(length=64),
            sa.ForeignKey("household_members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("dose_time", sa.Time(), nullable=False),
        sa.Column("days_of_week", postgresql.JSONB(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "ends_on IS NULL OR ends_on >= starts_on", name="ck_medication_entry_window"
        ),
    )
    op.create_index(
        "ix_medication_schedule_entries_person_id",
        "medication_schedule_entries",
        ["person_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_medication_schedule_entries_person_id", table_name="medication_schedule_entries"
    )
    op.drop_table("medication_schedule_entries")
