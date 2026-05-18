"""Alter rules.trigger_types from JSON to JSONB.

Revision ID: 0013
Revises: 0012_cts_alert_config
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_trigger_types_jsonb"
down_revision: str | None = "0012_cts_alert_config"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Use USING to cast existing data; JSONB is a strict superset.
    op.alter_column(
        "rules",
        "trigger_types",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(),
        existing_nullable=False,
        postgresql_using="trigger_types::jsonb",
    )


def downgrade() -> None:
    op.alter_column(
        "rules",
        "trigger_types",
        existing_type=postgresql.JSONB(),
        type_=sa.JSON(),
        existing_nullable=False,
        postgresql_using="trigger_types::json",
    )
