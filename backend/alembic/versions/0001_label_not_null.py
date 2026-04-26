"""pipeline_steps.label: allow NULL -> NOT NULL with default ''

PostgreSQL requires two steps to make a nullable column NOT NULL:
1. Backfill existing NULLs to the default value ('')
2. Alter the column to NOT NULL
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_label_not_null"
down_revision = "68d9e37c65c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill any existing NULL labels to empty string
    op.execute("UPDATE pipeline_steps SET label = '' WHERE label IS NULL")
    # Now set the column to NOT NULL with a server default
    op.alter_column(
        "pipeline_steps",
        "label",
        existing_type=sa.String(256),
        nullable=False,
        server_default="",
    )


def downgrade() -> None:
    op.alter_column(
        "pipeline_steps",
        "label",
        existing_type=sa.String(256),
        nullable=True,
        server_default=None,
    )
