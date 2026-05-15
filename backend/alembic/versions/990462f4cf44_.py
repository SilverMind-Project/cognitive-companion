"""Add question_order column to quiz_sessions.

Revision ID: 990462f4cf44
Revises: 0003
Create Date: 2026-05-14 16:40:00.798242

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "990462f4cf44"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "quiz_sessions",
        sa.Column(
            "question_order",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("quiz_sessions", "question_order")
