"""Add pipeline DAG schema.

Revision ID: 0002_add_pipeline_dag_schema
Revises: 0001_baseline
Create Date: 2026-06-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "0002_add_pipeline_dag_schema"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pipeline_steps",
        sa.Column("position_x", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "pipeline_steps",
        sa.Column("position_y", sa.Float(), nullable=False, server_default="0"),
    )

    op.create_table(
        "pipeline_edges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("source_step_id", sa.Integer(), nullable=False),
        sa.Column("source_port", sa.String(length=64), nullable=False),
        sa.Column("target_step_id", sa.Integer(), nullable=False),
        sa.Column("target_port", sa.String(length=64), server_default="main", nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_step_id"], ["pipeline_steps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_step_id"], ["pipeline_steps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_step_id", "source_port", name="uq_edge_source_port"),
    )
    op.create_index(
        op.f("ix_pipeline_edges_rule_id"),
        "pipeline_edges",
        ["rule_id"],
        unique=False,
    )

    conn = op.get_bind()

    conn.execute(
        text(
            """
            INSERT INTO pipeline_edges (
                rule_id,
                source_step_id,
                source_port,
                target_step_id,
                target_port
            )
            SELECT rule_id, id, 'true', next_step_on_true, 'main'
            FROM pipeline_steps
            WHERE next_step_on_true IS NOT NULL
            ON CONFLICT (source_step_id, source_port) DO NOTHING
            """
        )
    )

    conn.execute(
        text(
            """
            INSERT INTO pipeline_edges (
                rule_id,
                source_step_id,
                source_port,
                target_step_id,
                target_port
            )
            SELECT rule_id, id, 'false', next_step_on_false, 'main'
            FROM pipeline_steps
            WHERE next_step_on_false IS NOT NULL
            ON CONFLICT (source_step_id, source_port) DO NOTHING
            """
        )
    )

    conn.execute(
        text(
            """
            INSERT INTO pipeline_edges (
                rule_id,
                source_step_id,
                source_port,
                target_step_id,
                target_port
            )
            SELECT
                s.rule_id,
                s.id AS source_step_id,
                'main' AS source_port,
                (
                    SELECT ns.id
                    FROM pipeline_steps ns
                    WHERE ns.rule_id = s.rule_id
                      AND ns."order" > s."order"
                    ORDER BY ns."order" ASC
                    LIMIT 1
                ) AS target_step_id,
                'main' AS target_port
            FROM pipeline_steps s
            WHERE s.next_step_on_true IS NULL
              AND s.next_step_on_false IS NULL
              AND (
                  SELECT COUNT(*)
                  FROM pipeline_steps ns
                  WHERE ns.rule_id = s.rule_id
                    AND ns."order" > s."order"
              ) > 0
            ON CONFLICT (source_step_id, source_port) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_pipeline_edges_rule_id"), table_name="pipeline_edges")
    op.drop_table("pipeline_edges")
    op.drop_column("pipeline_steps", "position_y")
    op.drop_column("pipeline_steps", "position_x")
