"""Add nullable height_cm column with physical range check to household_members.

Revision ID: 0007_household_member_height_cm
Revises: 0006_wearables_registry
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_household_member_height_cm"
down_revision: str | Sequence[str] | None = "0006_wearables_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "household_members",
        sa.Column("height_cm", sa.Double(), nullable=True),
    )
    op.create_check_constraint(
        "ck_household_members_height_cm_range",
        "household_members",
        "height_cm IS NULL OR (height_cm >= 90.0 AND height_cm <= 220.0)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_household_members_height_cm_range",
        "household_members",
        type_="check",
    )
    op.drop_column("household_members", "height_cm")
