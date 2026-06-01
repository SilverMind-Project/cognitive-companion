"""Drop legacy pipeline step branch columns.

Revision ID: 0003_drop_branch_columns
Revises: 0002_add_pipeline_dag_schema
Create Date: 2026-06-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_drop_branch_columns"
down_revision: str | Sequence[str] | None = "0002_add_pipeline_dag_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "pipeline_steps_next_step_on_true_fkey",
        "pipeline_steps",
        type_="foreignkey",
    )
    op.drop_constraint(
        "pipeline_steps_next_step_on_false_fkey",
        "pipeline_steps",
        type_="foreignkey",
    )
    op.drop_column("pipeline_steps", "next_step_on_true")
    op.drop_column("pipeline_steps", "next_step_on_false")


def downgrade() -> None:
    op.add_column(
        "pipeline_steps",
        sa.Column("next_step_on_true", sa.Integer(), nullable=True),
    )
    op.add_column(
        "pipeline_steps",
        sa.Column("next_step_on_false", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "pipeline_steps_next_step_on_true_fkey",
        "pipeline_steps",
        "pipeline_steps",
        ["next_step_on_true"],
        ["id"],
    )
    op.create_foreign_key(
        "pipeline_steps_next_step_on_false_fkey",
        "pipeline_steps",
        "pipeline_steps",
        ["next_step_on_false"],
        ["id"],
    )
