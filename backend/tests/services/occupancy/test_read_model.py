"""Unit tests for the unified OccupancyReadModel."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.services.occupancy import OccupancyReadModel


@pytest.mark.asyncio
async def test_identified_and_unknown_aggregate_per_room():
    model = OccupancyReadModel()
    now = datetime.now(UTC)
    model.record_room_presence(
        room_id=1, room_name="kitchen", ph_id="ph-a", identity_id="alice", observed_at=now
    )
    model.record_room_presence(
        room_id=1, room_name="kitchen", ph_id="ph-x", identity_id=None, observed_at=now
    )

    records = await model.get_occupancy()
    assert len(records) == 1
    rec = records[0]
    assert rec.room_id == 1
    assert rec.room_name == "kitchen"
    assert rec.occupied is True
    assert rec.person_ids == ["alice"]
    assert rec.unknown_count == 1
    assert rec.source == "world_tracker"


@pytest.mark.asyncio
async def test_stale_hypothesis_is_pruned_on_read():
    model = OccupancyReadModel(ttl_seconds=60)
    old = datetime.now(UTC) - timedelta(seconds=120)
    model.record_room_presence(
        room_id=1, room_name="kitchen", ph_id="ph-a", identity_id="alice", observed_at=old
    )

    assert await model.get_occupancy() == []


@pytest.mark.asyncio
async def test_hypothesis_moves_rooms_no_double_count():
    model = OccupancyReadModel()
    now = datetime.now(UTC)
    model.record_room_presence(
        room_id=1, room_name="kitchen", ph_id="ph-a", identity_id="alice", observed_at=now
    )
    model.record_room_presence(
        room_id=2, room_name="bedroom", ph_id="ph-a", identity_id="alice", observed_at=now
    )

    records = await model.get_occupancy()
    assert len(records) == 1
    assert records[0].room_name == "bedroom"


@pytest.mark.asyncio
async def test_room_name_filter():
    model = OccupancyReadModel()
    now = datetime.now(UTC)
    model.record_room_presence(
        room_id=1, room_name="kitchen", ph_id="ph-a", identity_id="alice", observed_at=now
    )
    model.record_room_presence(
        room_id=2, room_name="bedroom", ph_id="ph-b", identity_id="bob", observed_at=now
    )

    records = await model.get_occupancy(room_name="bedroom")
    assert [r.room_name for r in records] == ["bedroom"]


def _db_factory_with_rows(rows):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = rows
    return lambda: db


@pytest.mark.asyncio
async def test_ha_sensor_rows_merged_and_world_tracker_wins():
    now = datetime.now(UTC)
    ha_rows = [
        SimpleNamespace(
            room_name="bathroom",
            occupied=True,
            person_ids=[],
            source="ha_sensor",
            since=now,
            last_updated=now,
        ),
        # Same room as a live world-tracker room: the tracker must win.
        SimpleNamespace(
            room_name="kitchen",
            occupied=False,
            person_ids=[],
            source="ha_sensor",
            since=None,
            last_updated=now,
        ),
    ]
    model = OccupancyReadModel(db_factory=_db_factory_with_rows(ha_rows))
    model.record_room_presence(
        room_id=1, room_name="kitchen", ph_id="ph-a", identity_id="alice", observed_at=now
    )

    records = {r.room_name: r for r in await model.get_occupancy()}
    assert set(records) == {"kitchen", "bathroom"}
    assert records["kitchen"].source == "world_tracker"  # tracker wins
    assert records["bathroom"].source == "ha_sensor"
