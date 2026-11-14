"""Drop the operator-edited camera adjacency graph.

Tracking stopped reading operator adjacency edges when the old cross-camera associator was
removed; walk times between cameras are learned by the tracking orchestrator, and cameras that
see the same floor area are declared as overlap groups (``cts_camera_overlap_groups``). The
column had no reader. The downgrade restores an empty column; the edges themselves are not
recoverable and had no effect.

Revision ID: 0004_drop_cts_adjacency_edges
Revises: 0003_cts_camera_face_raw_similarity
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_drop_cts_adjacency_edges"
down_revision: str | Sequence[str] | None = "0003_cts_camera_face_raw_similarity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("household_settings", "cts_adjacency_edges")


def downgrade() -> None:
    op.add_column("household_settings", sa.Column("cts_adjacency_edges", sa.JSON(), nullable=True))
