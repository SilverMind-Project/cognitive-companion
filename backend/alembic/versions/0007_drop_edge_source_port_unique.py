"""Drop the unique constraint on pipeline_edges (source_step_id, source_port).

A single step output port may now fan out to multiple target steps, so the
one-target-per-port uniqueness no longer holds. Traversal order and join
semantics are handled by the in-degree-gated DAG executor.

Revision ID: 0007_drop_edge_source_port_unique
Revises: 0006_signal_feedback
Create Date: 2026-06-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_edge_port_fanout"
down_revision: str | Sequence[str] | None = "0006_signal_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_edge_source_port", "pipeline_edges", type_="unique")


def downgrade() -> None:
    # Re-adding the constraint requires that no port currently fans out to more
    # than one target; deduplicate pipeline_edges before downgrading if so.
    op.create_unique_constraint(
        "uq_edge_source_port",
        "pipeline_edges",
        ["source_step_id", "source_port"],
    )
