"""Add room_occupancy_state table for unified occupancy tracking.

Revision ID: 0014
Revises: 0013_trigger_types_jsonb
Create Date: 2026-05-19
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0014_room_occupancy_state"
down_revision: str | None = "0013_trigger_types_jsonb"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "room_occupancy_state",
        sa.Column("room_name", sa.String(128), primary_key=True),
        sa.Column("occupied", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("person_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("room_occupancy_state")
