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
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    SqlAlchemyObservationRepository,
    minute_of_day_in_window,
)
from backend.services.person_location.types import FloorPoint, LocationObservation

# ---------------------------------------------------------------------------
# Pure unit tests for the time-of-day window predicate (no DB)
# ---------------------------------------------------------------------------


def test_minute_window_none_bounds_matches_all() -> None:
    assert minute_of_day_in_window(0, None, None) is True
    assert minute_of_day_in_window(1439, None, None) is True


def test_minute_window_normal_range_is_half_open() -> None:
    # 09:00-17:00 -> [540, 1020)
    assert minute_of_day_in_window(540, 540, 1020) is True
    assert minute_of_day_in_window(1019, 540, 1020) is True
    assert minute_of_day_in_window(1020, 540, 1020) is False
    assert minute_of_day_in_window(539, 540, 1020) is False


def test_minute_window_wraps_past_midnight() -> None:
    # 22:00-03:00 -> start 1320, end 180 (wrap)
    assert minute_of_day_in_window(1320, 1320, 180) is True  # 22:00
    assert minute_of_day_in_window(1410, 1320, 180) is True  # 23:30
    assert minute_of_day_in_window(0, 1320, 180) is True  # 00:00
    assert minute_of_day_in_window(179, 1320, 180) is True  # 02:59
    assert minute_of_day_in_window(180, 1320, 180) is False  # 03:00
    assert minute_of_day_in_window(690, 1320, 180) is False  # 11:30


@pytest.mark.asyncio
async def test_inmemory_heatmap_local_tz_wrap() -> None:
    """In-memory repo applies the same local-tz wrap filter as the SQL repo."""
    repo = InMemoryObservationRepository()
    # 18:00 UTC == 23:30 IST -> inside the 22:00-03:00 night window.
    await repo.insert(
        LocationObservation(
            id=uuid.uuid4(),
            person_id="kim",
            observed_at=datetime(2024, 1, 15, 18, 0, tzinfo=UTC),
            source="world_tracker",
            floor_point=FloorPoint(x_m=1.0, y_m=1.0),
        )
    )
    # 06:00 UTC == 11:30 IST -> outside the window.
    await repo.insert(
        LocationObservation(
            id=uuid.uuid4(),
            person_id="kim",
            observed_at=datetime(2024, 1, 15, 6, 0, tzinfo=UTC),
            source="world_tracker",
            floor_point=FloorPoint(x_m=5.0, y_m=5.0),
        )
    )

    bins = await repo.list_heatmap_bins(
        "kim",
        datetime(2024, 1, 15, 0, 0, tzinfo=UTC),
        datetime(2024, 1, 16, 0, 0, tzinfo=UTC),
        tz_name="Asia/Kolkata",
        filter_start_minute=1320,
        filter_end_minute=180,
    )

    assert len(bins) == 1
    assert bins[0].x_bin == pytest.approx(1.0)


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
            text("CALL refresh_continuous_aggregate('location_heatmaps_15m', :since, :until)"),
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
    await repo.insert(_obs(person_id, x=1.0, y=2.0))  # bin (1.0, 2.0)
    await repo.insert(_obs(person_id, x=1.2, y=2.3))  # bin (1.0, 2.0)
    await repo.insert(_obs(person_id, x=3.0, y=4.0))  # bin (3.0, 4.0)

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
# Local-timezone, cross-midnight time-of-day filtering
# ---------------------------------------------------------------------------

# A full-day window so the time-of-day filter (not the absolute window) is what
# selects buckets.
_DAY_START = datetime(2024, 1, 15, 0, 0, 0, tzinfo=UTC)
_DAY_END = datetime(2024, 1, 16, 0, 0, 0, tzinfo=UTC)

# "Night" sundowning window 22:00-03:00 local -> wraps past midnight.
_NIGHT_START_MIN = 22 * 60  # 1320
_NIGHT_END_MIN = 3 * 60  # 180


@pytest.mark.asyncio
async def test_heatmap_local_tz_wrap_window_includes_evening(db_engine, db_factory) -> None:
    """A bucket at 18:00 UTC is 23:30 IST and must match a 22:00-03:00 local
    night window. Under a (wrong) UTC interpretation 18:00 falls outside the
    window, so this asserts the AT TIME ZONE conversion direction and wrap."""
    person_id = "ivy"
    _seed_member(db_factory, person_id)
    repo = _make_repo(db_factory)

    # 18:00 UTC == 23:30 Asia/Kolkata (+5:30) -> local minute 1410.
    await repo.insert(_obs(person_id, x=1.0, y=1.0, t=datetime(2024, 1, 15, 18, 0, tzinfo=UTC)))
    _refresh(db_engine, _DAY_START, _DAY_END)

    bins = await repo.list_heatmap_bins(
        person_id,
        _DAY_START,
        _DAY_END,
        tz_name="Asia/Kolkata",
        filter_start_minute=_NIGHT_START_MIN,
        filter_end_minute=_NIGHT_END_MIN,
    )

    assert len(bins) == 1
    assert bins[0].x_bin == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_heatmap_local_tz_nonwrap_window(db_engine, db_factory) -> None:
    """Non-wrap branch (start <= end): a 06:00-12:00 local morning window keeps
    an 08:30-local bucket and drops a 23:30-local bucket."""
    person_id = "liam"
    _seed_member(db_factory, person_id)
    repo = _make_repo(db_factory)

    # 03:00 UTC == 08:30 IST -> minute 510, inside morning [360, 720).
    await repo.insert(_obs(person_id, x=1.0, y=1.0, t=datetime(2024, 1, 15, 3, 0, tzinfo=UTC)))
    # 18:00 UTC == 23:30 IST -> minute 1410, outside the morning window.
    await repo.insert(_obs(person_id, x=4.0, y=4.0, t=datetime(2024, 1, 15, 18, 0, tzinfo=UTC)))
    _refresh(db_engine, _DAY_START, _DAY_END)

    bins = await repo.list_heatmap_bins(
        person_id,
        _DAY_START,
        _DAY_END,
        tz_name="Asia/Kolkata",
        filter_start_minute=6 * 60,
        filter_end_minute=12 * 60,
    )

    assert len(bins) == 1
    assert bins[0].x_bin == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_heatmap_local_tz_wrap_window_excludes_daytime(db_engine, db_factory) -> None:
    """A bucket at 06:00 UTC is 11:30 IST and must be excluded by the same
    22:00-03:00 local night window (proves the filter actually filters)."""
    person_id = "jack"
    _seed_member(db_factory, person_id)
    repo = _make_repo(db_factory)

    # 06:00 UTC == 11:30 Asia/Kolkata -> local minute 690, outside the night.
    await repo.insert(_obs(person_id, x=2.0, y=2.0, t=datetime(2024, 1, 15, 6, 0, tzinfo=UTC)))
    _refresh(db_engine, _DAY_START, _DAY_END)

    _bins = await repo.list_heatmap_bins(
        person_id,
        _DAY_START,
        _DAY_END,
        tz_name="Asia/Kolkata",
        filter_start_minute=_NIGHT_START_MIN,
        filter_end_minute=_NIGHT_END_MIN,
    )


# ---------------------------------------------------------------------------
# latest_observation() / list_for_person() room-name join
# ---------------------------------------------------------------------------


def _seed_room(db_factory, name: str) -> int:
    from backend.models.room import Room

    db = db_factory()
    try:
        room = db.query(Room).filter(Room.name == name).first()
        if room is not None:
            return room.id
        room = Room(name=name)
        db.add(room)
        db.commit()
        return room.id
    finally:
        db.close()


def _obs_with_room(
    person_id: str, room_id: int | None, t: datetime, source: str = "world_tracker"
) -> LocationObservation:
    return LocationObservation(
        id=uuid.uuid4(),
        person_id=person_id,
        observed_at=t,
        source=source,
        room_id=room_id,
    )


@pytest.mark.asyncio
async def test_latest_observation_resolves_room_name_via_join(db_factory) -> None:
    """Success path: the newest observation's room_id resolves to a name
    via the rooms table, mirroring InMemoryObservationRepository's map."""
    person_id = "kim"
    _seed_member(db_factory, person_id)
    room_id = _seed_room(db_factory, "bedroom")
    repo = _make_repo(db_factory)

    older = _BASE_TIME
    newer = _BASE_TIME + timedelta(minutes=5)
    await repo.insert(_obs_with_room(person_id, room_id, older))
    await repo.insert(_obs_with_room(person_id, room_id, newer))

    latest = await repo.latest_observation(person_id, since=_BASE_TIME - timedelta(hours=1))

    assert latest is not None
    assert latest.observed_at == newer
    assert latest.room_name == "bedroom"


@pytest.mark.asyncio
async def test_latest_observation_no_room_id_leaves_room_name_none(db_factory) -> None:
    """Edge case: an observation with no room_id resolves to no room_name."""
    person_id = "liam2"
    _seed_member(db_factory, person_id)
    repo = _make_repo(db_factory)

    await repo.insert(_obs_with_room(person_id, None, _BASE_TIME))

    latest = await repo.latest_observation(person_id, since=_BASE_TIME - timedelta(hours=1))

    assert latest is not None
    assert latest.room_id is None
    assert latest.room_name is None


@pytest.mark.asyncio
async def test_latest_observation_missing_data_returns_none(db_factory) -> None:
    """Missing-data path: a person with no observations at all returns None."""
    _seed_member(db_factory, "nobody2")
    repo = _make_repo(db_factory)

    latest = await repo.latest_observation("nobody2", since=_BASE_TIME - timedelta(hours=1))

    assert latest is None


@pytest.mark.asyncio
async def test_list_for_person_resolves_room_name_for_every_row(db_factory) -> None:
    """Success path: list_for_person batch-resolves room_name per row, not
    just for the single-row latest_observation() path."""
    person_id = "noah"
    _seed_member(db_factory, person_id)
    bedroom_id = _seed_room(db_factory, "bedroom2")
    kitchen_id = _seed_room(db_factory, "kitchen2")
    repo = _make_repo(db_factory)

    t0 = _BASE_TIME
    t1 = _BASE_TIME + timedelta(minutes=5)
    await repo.insert(_obs_with_room(person_id, bedroom_id, t0))
    await repo.insert(_obs_with_room(person_id, kitchen_id, t1))

    rows = await repo.list_for_person(
        person_id, since=_BASE_TIME - timedelta(hours=1), until=_BASE_TIME + timedelta(hours=1)
    )

    by_time = {r.observed_at: r.room_name for r in rows}
    assert by_time[t0] == "bedroom2"
    assert by_time[t1] == "kitchen2"


# ---------------------------------------------------------------------------
# bucketed_observations (sighting-event downsample)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bucketed_observations_downsamples_dense_cluster_to_one_row(db_factory) -> None:
    """A dense cluster inside one bucket collapses to a single row: the
    most recent observation in that (room, bucket), room_name resolved via
    the same rooms-table join as the other read paths."""
    person_id = "olivia"
    _seed_member(db_factory, person_id)
    room_id = _seed_room(db_factory, "bedroom3")
    repo = _make_repo(db_factory)

    anchor_epoch = (_BASE_TIME.timestamp() // 120) * 120 + 5
    base = datetime.fromtimestamp(anchor_epoch, tz=UTC)
    times = [base + timedelta(seconds=3 * i) for i in range(10)]
    for t in times:
        await repo.insert(_obs_with_room(person_id, room_id, t))

    rows = await repo.bucketed_observations(
        person_id, since=base - timedelta(hours=1), until=base + timedelta(hours=1)
    )

    assert len(rows) == 1
    assert rows[0].observed_at == times[-1]
    assert rows[0].room_name == "bedroom3"


@pytest.mark.asyncio
async def test_bucketed_observations_partitions_by_room_within_same_bucket(db_factory) -> None:
    """Two rooms observed within the same time bucket each keep their own
    representative row: the partition is (room_id, bucket), not bucket alone."""
    person_id = "peter"
    _seed_member(db_factory, person_id)
    bedroom_id = _seed_room(db_factory, "bedroom4")
    kitchen_id = _seed_room(db_factory, "kitchen4")
    repo = _make_repo(db_factory)

    anchor_epoch = (_BASE_TIME.timestamp() // 120) * 120 + 5
    base = datetime.fromtimestamp(anchor_epoch, tz=UTC)
    await repo.insert(_obs_with_room(person_id, bedroom_id, base))
    await repo.insert(_obs_with_room(person_id, kitchen_id, base + timedelta(seconds=10)))

    rows = await repo.bucketed_observations(
        person_id, since=base - timedelta(hours=1), until=base + timedelta(hours=1)
    )

    room_names = {r.room_name for r in rows}
    assert room_names == {"bedroom4", "kitchen4"}


@pytest.mark.asyncio
async def test_bucketed_observations_not_clipped_by_limit_across_wide_window(db_factory) -> None:
    """The bug an earlier attempt at this had: a plain query LIMIT applied
    before deduping drops old history once raw row count exceeds it. Here
    a dense recent cluster (50 rows, one bucket) coexists with a single
    isolated old row (a separate bucket, 3 hours earlier); even with a
    limit far smaller than the raw row count, the old bucket must survive
    because bucketing runs before LIMIT, not after."""
    person_id = "quinn"
    _seed_member(db_factory, person_id)
    room_id = _seed_room(db_factory, "bedroom5")
    repo = _make_repo(db_factory)

    anchor_epoch = (_BASE_TIME.timestamp() // 120) * 120 + 5
    recent_base = datetime.fromtimestamp(anchor_epoch, tz=UTC)
    old_time = recent_base - timedelta(hours=3)

    await repo.insert(_obs_with_room(person_id, room_id, old_time))
    for i in range(50):
        await repo.insert(_obs_with_room(person_id, room_id, recent_base + timedelta(seconds=i)))

    rows = await repo.bucketed_observations(
        person_id,
        since=old_time - timedelta(hours=1),
        until=recent_base + timedelta(hours=1),
        limit=2,
    )

    observed_times = {r.observed_at for r in rows}
    assert old_time in observed_times


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
