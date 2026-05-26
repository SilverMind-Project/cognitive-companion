"""Create location_observations and presence_segments tables (M4).

Revision ID: 0018_unified_location
Revises: 0017_calibration_health_and_transit_zones
Create Date: 2026-05-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0018_unified_location"
down_revision: str | None = "0017_calibration_health_and_transit_zones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "location_observations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "person_id",
            UUID,
            sa.ForeignKey("household_members.id"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("floor_x_m", sa.Float(), nullable=True),
        sa.Column("floor_y_m", sa.Float(), nullable=True),
        sa.Column("room_id", UUID, sa.ForeignKey("rooms.id"), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.execute(
        "SELECT create_hypertable('location_observations', 'observed_at', "
        "chunk_time_interval => INTERVAL '6 hours', if_not_exists => TRUE)"
    )
    op.create_index(
        "idx_loc_obs_person",
        "location_observations",
        ["person_id", "observed_at"],
        postgresql_ordering={"observed_at": "DESC"},
    )
    op.create_index(
        "idx_loc_obs_room",
        "location_observations",
        ["room_id", "observed_at"],
        postgresql_ordering={"observed_at": "DESC"},
    )

    op.create_table(
        "presence_segments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "person_id",
            UUID,
            sa.ForeignKey("household_members.id"),
            nullable=False,
        ),
        sa.Column("room_id", UUID, sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entry_source", sa.String(32), nullable=False),
        sa.Column("exit_source", sa.String(32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "superseded_by", UUID, sa.ForeignKey("presence_segments.id"), nullable=True
        ),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index(
        "idx_ps_person_open",
        "presence_segments",
        ["person_id"],
        postgresql_where=sa.text("exited_at IS NULL"),
    )
    op.create_index(
        "idx_ps_person_time",
        "presence_segments",
        ["person_id", "entered_at"],
        postgresql_ordering={"entered_at": "DESC"},
    )
    op.create_index(
        "idx_ps_room_time",
        "presence_segments",
        ["room_id", "entered_at"],
        postgresql_ordering={"entered_at": "DESC"},
    )


def downgrade() -> None:
    op.drop_table("presence_segments")
    op.drop_table("location_observations")
