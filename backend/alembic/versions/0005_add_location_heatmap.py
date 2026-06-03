"""Add location_heatmaps_15m continuous aggregate for spatial density heatmaps.

Revision ID: 0005_add_location_heatmap
Revises: 0004_drop_emergency_alerts
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "0005_add_location_heatmap"
down_revision: str | Sequence[str] | None = "0004_drop_emergency_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE_CAGG = """
CREATE MATERIALIZED VIEW location_heatmaps_15m
WITH (timescaledb.continuous) AS
SELECT
    person_id,
    time_bucket('15 minutes', observed_at) AS time_bucket_15m,
    floor(floor_x_m / 0.5) * 0.5 AS x_bin,
    floor(floor_y_m / 0.5) * 0.5 AS y_bin,
    count(*) AS weight
FROM location_observations
WHERE floor_x_m IS NOT NULL AND floor_y_m IS NOT NULL
GROUP BY 1, 2, 3, 4
WITH NO DATA
"""

_ADD_POLICY = """
SELECT add_continuous_aggregate_policy('location_heatmaps_15m',
    start_offset => INTERVAL '3 days',
    end_offset   => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes')
"""

_REMOVE_POLICY = "SELECT remove_continuous_aggregate_policy('location_heatmaps_15m')"
_DROP_CAGG = "DROP MATERIALIZED VIEW location_heatmaps_15m"


def upgrade() -> None:
    op.execute(text(_CREATE_CAGG))
    op.execute(text(_ADD_POLICY))


def downgrade() -> None:
    op.execute(text(_REMOVE_POLICY))
    op.execute(text(_DROP_CAGG))
