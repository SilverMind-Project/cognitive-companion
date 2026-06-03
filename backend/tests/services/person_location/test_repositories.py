"""Integration tests for SqlAlchemyObservationRepository.list_heatmap_bins.

Uses a real TimescaleDB testcontainer.  The module-scoped fixture creates the
location_heatmaps_15m continuous aggregate using the same DDL as the Alembic
migration.  Each test inserts observations via the repository, manually
refreshes the aggregate (the background policy worker does not run in tests),
then queries and asserts.

Test timestamps are fixed in 2024-01 (well in the past) to avoid hitting
TimescaleDB's end_offset watermark edge cases.

The last test in this module performs a downgrade/upgrade round-trip using the
exact migration SQL to confirm both paths work.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from backend.models.person import HouseholdMember
from backend.services.person_location.repositories import SqlAlchemyObservationRepository
from backend.services.person_location.types import FloorPoint, LocationObservation

# ---------------------------------------------------------------------------
# Exact migration SQL -- must stay byte-for-byte identical to
# backend/alembic/versions/0005_add_location_heatmap.py
# ---------------------------------------------------------------------------

_MIGRATION_CREATE_CAGG = """
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

_MIGRATION_ADD_POLICY = """
SELECT add_continuous_aggregate_policy('location_heatmaps_15m',
    start_offset => INTERVAL '3 days',
    end_offset   => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes')
"""

_MIGRATION_REMOVE_POLICY = "SELECT remove_continuous_aggregate_policy('location_heatmaps_15m')"
_MIGRATION_DROP_CAGG = "DROP MATERIALIZED VIEW location_heatmaps_15m"

# Base window used by all tests -- far enough in the past that there are no
# watermark concerns, and wide enough to capture any 15-minute bucket.
_BASE_TIME = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
_WINDOW_START = _BASE_TIME - timedelta(hours=1)
_WINDOW_END = _BASE_TIME + timedelta(hours=2)


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _heatmap_cagg(db_engine):
    """Create the continuous aggregate once per module using exact migration SQL."""
    with db_engine.connect() as conn:
        conn.execute(text(_MIGRATION_CREATE_CAGG))
        conn.execute(text(_MIGRATION_ADD_POLICY))
        conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(db_factory) -> SqlAlchemyObservationRepository:
    return SqlAlchemyObservationRepository(db_factory)


def _seed_member(db_factory, person_id: str) -> None:
    db = db_factory()
    try:
        if db.get(HouseholdMember, person_id) is None:
            db.add(HouseholdMember(id=person_id, name=person_id.title()))
            db.commit()
    finally:
        db.close()


def _obs(person_id: str, x: float, y: float, t: datetime | None = None) -> LocationObservation:
    return LocationObservation(
        id=uuid.uuid4(),
        person_id=person_id,
        observed_at=t or _BASE_TIME,
        source="world_tracker",
        floor_point=FloorPoint(x_m=x, y_m=y),
    )


def _refresh(db_engine, since: datetime, until: datetime) -> None:
    # refresh_continuous_aggregate must run outside a transaction block.
    with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(
            text(
                "CALL refresh_continuous_aggregate("
                "'location_heatmaps_15m', :since, :until)"
            ),
            {"since": since, "until": until},
        )


def _cagg_exists(db_engine) -> bool:
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM pg_class WHERE relname = 'location_heatmaps_15m'")
        ).scalar()
    return bool(row)


# ---------------------------------------------------------------------------
# Functional tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_observations_aggregate_into_spatial_bins(db_engine, db_factory) -> None:
    """Multiple observations within 0.5 m of each other collapse to one bin."""
    person_id = "alice"
    _seed_member(db_factory, person_id)
    repo = _make_repo(db_factory)

    # Two points in the same 0.5-m bin (x_bin=1.0, y_bin=2.0), one in another.
    await repo.insert(_obs(person_id, x=1.0, y=2.0))   # bin (1.0, 2.0)
    await repo.insert(_obs(person_id, x=1.2, y=2.3))   # bin (1.0, 2.0)
    await repo.insert(_obs(person_id, x=3.0, y=4.0))   # bin (3.0, 4.0)

    _refresh(db_engine, _WINDOW_START, _WINDOW_END)

    bins = await repo.list_heatmap_bins(person_id, _WINDOW_START, _WINDOW_END)

    by_key = {(b.x_bin, b.y_bin): b.weight for b in bins}
    assert by_key.get((1.0, 2.0)) == 2
    assert by_key.get((3.0, 4.0)) == 1
    assert len(bins) == 2


@pytest.mark.asyncio
async def test_no_observations_returns_empty(db_engine, db_factory) -> None:
    """Query for a person with no observations returns an empty list."""
    _seed_member(db_factory, "bob")
    repo = _make_repo(db_factory)

    _refresh(db_engine, _WINDOW_START, _WINDOW_END)

    bins = await repo.list_heatmap_bins("bob", _WINDOW_START, _WINDOW_END)

    assert bins == []


@pytest.mark.asyncio
async def test_observations_outside_range_excluded(db_engine, db_factory) -> None:
    """Observations outside the queried window are not returned."""
    person_id = "carol"
    _seed_member(db_factory, person_id)
    repo = _make_repo(db_factory)

    in_range_time = _BASE_TIME
    out_of_range_time = _BASE_TIME + timedelta(hours=4)  # outside _WINDOW_END

    await repo.insert(_obs(person_id, x=1.0, y=1.0, t=in_range_time))
    await repo.insert(_obs(person_id, x=5.0, y=5.0, t=out_of_range_time))

    # Refresh covering both timestamps so both are materialised.
    _refresh(db_engine, _WINDOW_START, _WINDOW_END + timedelta(hours=4))

    bins = await repo.list_heatmap_bins(person_id, _WINDOW_START, _WINDOW_END)

    assert len(bins) == 1
    assert bins[0].x_bin == pytest.approx(1.0)
    assert bins[0].y_bin == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_weight_sorted_descending(db_engine, db_factory) -> None:
    """list_heatmap_bins returns bins sorted by weight descending."""
    person_id = "dave"
    _seed_member(db_factory, person_id)
    repo = _make_repo(db_factory)

    # Bin (2.0, 2.0) gets 3 hits; bin (0.0, 0.0) gets 1 hit.
    for _ in range(3):
        await repo.insert(_obs(person_id, x=2.1, y=2.2))
    await repo.insert(_obs(person_id, x=0.1, y=0.2))

    _refresh(db_engine, _WINDOW_START, _WINDOW_END)

    bins = await repo.list_heatmap_bins(person_id, _WINDOW_START, _WINDOW_END)

    assert len(bins) == 2
    assert bins[0].weight >= bins[1].weight
    assert bins[0].weight == 3


# ---------------------------------------------------------------------------
# Migration round-trip test -- runs last so functional tests above are not
# affected by the temporary teardown.
# ---------------------------------------------------------------------------


def test_migration_upgrade_downgrade_cycle(db_engine) -> None:
    """Exact upgrade() and downgrade() SQL from 0005_add_location_heatmap round-trips."""
    assert _cagg_exists(db_engine), "CAGG should exist (created by module fixture)"

    # downgrade: remove policy then drop the view
    with db_engine.connect() as conn:
        conn.execute(text(_MIGRATION_REMOVE_POLICY))
        conn.execute(text(_MIGRATION_DROP_CAGG))
        conn.commit()

    assert not _cagg_exists(db_engine), "CAGG should be gone after downgrade"

    # upgrade: re-create using exact migration SQL (no IF NOT EXISTS)
    with db_engine.connect() as conn:
        conn.execute(text(_MIGRATION_CREATE_CAGG))
        conn.execute(text(_MIGRATION_ADD_POLICY))
        conn.commit()

    assert _cagg_exists(db_engine), "CAGG should be restored after upgrade"
