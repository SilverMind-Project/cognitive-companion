"""Unit tests for :class:`PresenceQueryHandler`.

Exercises the step's main branches:
- unknown person (graceful no-op)
- PRESENT_ROOM status → flat keys correct
- ASLEEP status → presence_asleep=true
- AWAY status → presence_away=true
- Signal filter respects signal_kind
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from backend.services.presence import PresenceSnapshot, PresenceSource, PresenceStatus
from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.presence_query import PresenceQueryHandler


@dataclass
class _FakeExecution:
    id: int = 1


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)


def _make_trigger() -> TriggerContext:
    return TriggerContext(trigger_type="manual")


def _make_snapshot(
    status: PresenceStatus,
    room_name: str | None = "kitchen",
    confidence: float = 0.9,
) -> PresenceSnapshot:
    return PresenceSnapshot(
        person_id="mom",
        status=status,
        room_id="k1" if room_name else None,
        room_name=room_name,
        confidence=confidence,
        last_seen_at=datetime.now(UTC) - timedelta(minutes=5),
        dwell_minutes=12.5,
        sources=(PresenceSource(name="location_service", confidence=0.9),),
        inferred_at=datetime.now(UTC),
        notes=None,
    )


class _StubPresenceService:
    def __init__(self, snapshot: PresenceSnapshot | None = None) -> None:
        self.snapshot = snapshot

    async def get(self, person_id: str, *, at: datetime | None = None) -> PresenceSnapshot:
        if self.snapshot is None:
            return PresenceSnapshot(
                person_id=person_id,
                status=PresenceStatus.UNKNOWN,
                room_id=None,
                room_name=None,
                confidence=0.0,
                last_seen_at=None,
                dwell_minutes=None,
                sources=(),
                inferred_at=datetime.now(UTC),
            )
        return self.snapshot


def _make_services(
    presence=None,
) -> ServiceContainer:
    return ServiceContainer(
        db_factory=lambda: None,
        presence=presence,
        semantic_memory_client=None,
    )


@pytest.mark.asyncio
async def test_no_person_returns_available_false():
    handler = PresenceQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": ""}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=_make_services(),
    )
    assert result.success
    assert result.data.get("presence_available") is False
    assert result.data.get("presence_at_home") is False
    assert result.data.get("presence_asleep") is False


@pytest.mark.asyncio
async def test_present_room_flat_keys():
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM, room_name="kitchen")
    services = _make_services(_StubPresenceService(snapshot))
    handler = PresenceQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": "mom"}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )
    data = result.data
    assert data["presence_available"] is True
    assert data["presence_status"] == "present_room"
    assert data["presence_room_name"] == "kitchen"
    assert data["presence_at_home"] is True
    assert data["presence_asleep"] is False
    assert data["presence_away"] is False
    assert data["presence_dwell_minutes"] == 12.5


@pytest.mark.asyncio
async def test_asleep_status():
    snapshot = _make_snapshot(PresenceStatus.ASLEEP, room_name="bedroom")
    services = _make_services(_StubPresenceService(snapshot))
    handler = PresenceQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": "mom"}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )
    data = result.data
    assert data["presence_status"] == "asleep"
    assert data["presence_at_home"] is True
    assert data["presence_asleep"] is True
    assert data["presence_away"] is False


@pytest.mark.asyncio
async def test_away_status():
    snapshot = _make_snapshot(PresenceStatus.AWAY, room_name=None, confidence=0.8)
    services = _make_services(_StubPresenceService(snapshot))
    handler = PresenceQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": "mom"}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )
    data = result.data
    assert data["presence_status"] == "away"
    assert data["presence_at_home"] is False
    assert data["presence_asleep"] is False
    assert data["presence_away"] is True


@pytest.mark.asyncio
async def test_custom_output_key():
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM, room_name="kitchen")
    services = _make_services(_StubPresenceService(snapshot))
    handler = PresenceQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": "mom", "output_key": "loc"}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )
    data = result.data
    assert data["loc_available"] is True
    assert data["loc_status"] == "present_room"
    assert data["loc_room_name"] == "kitchen"
    # Flat keys always use "presence_" prefix.
    assert data["presence_status"] == "present_room"


@pytest.mark.asyncio
async def test_pipeline_data_fallback_person_id():
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM, room_name="kitchen")
    services = _make_services(_StubPresenceService(snapshot))
    handler = PresenceQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={}),
        execution=_FakeExecution(),
        pipeline_data={"persons": [{"person_id": "mom"}]},
        trigger=_make_trigger(),
        services=services,
    )
    assert result.data["presence_available"] is True
    assert result.data["presence_status"] == "present_room"


@pytest.mark.asyncio
async def test_no_presence_service_returns_false():
    handler = PresenceQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": "mom"}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=ServiceContainer(db_factory=lambda: None),
    )
    assert result.data["presence_available"] is False


# ---------------------------------------------------------------------------
# room_dwell_history mode (DL-M08 Part B)
# ---------------------------------------------------------------------------


@dataclass
class _FakeRoom:
    id: int
    name: str


class _StubPersonLocationService:
    def __init__(self, episodes=()):
        self.episodes = episodes
        self.calls: list[dict] = []

    async def dwell_episodes(self, person_id, room_id, start, end, *, now=None, merge_gap_s=120):
        self.calls.append(
            {
                "person_id": person_id,
                "room_id": room_id,
                "start": start,
                "end": end,
                "now": now,
                "merge_gap_s": merge_gap_s,
            }
        )
        return self.episodes


def _make_mock_db(room: _FakeRoom | None):
    from unittest.mock import MagicMock

    session = MagicMock()
    session.query.return_value = session
    session.filter.return_value = session
    session.first.return_value = room
    return session


@dataclass
class _FakeEpisode:
    entered_at: datetime
    exited_at: datetime
    minutes: float


def _history_config(**overrides) -> dict:
    config = {
        "query_mode": "room_dwell_history",
        "person_id": "mom",
        "room_name": "bathroom",
    }
    config.update(overrides)
    return config


@pytest.mark.asyncio
async def test_room_dwell_history_qualifying_episode_found():
    room = _FakeRoom(id=7, name="bathroom")
    db = _make_mock_db(room)
    episodes = (_FakeEpisode(datetime.now(UTC), datetime.now(UTC), 10.0),)
    person_location = _StubPersonLocationService(episodes)
    services = ServiceContainer(db_factory=lambda: db, person_location=person_location)

    handler = PresenceQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json=_history_config(min_episode_minutes=8)),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )

    assert result.data["presence_had_dwell"] is True
    assert result.data["presence_qualifying_episodes"] == 1
    assert result.data["presence_total_minutes"] == 10.0
    assert result.data["presence_longest_minutes"] == 10.0
    assert person_location.calls[0]["person_id"] == "mom"
    assert person_location.calls[0]["room_id"] == 7


@pytest.mark.asyncio
async def test_room_dwell_history_below_threshold_episode_excluded():
    room = _FakeRoom(id=7, name="bathroom")
    db = _make_mock_db(room)
    episodes = (_FakeEpisode(datetime.now(UTC), datetime.now(UTC), 3.0),)
    person_location = _StubPersonLocationService(episodes)
    services = ServiceContainer(db_factory=lambda: db, person_location=person_location)

    handler = PresenceQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json=_history_config(min_episode_minutes=8)),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )

    assert result.data["presence_had_dwell"] is False
    assert result.data["presence_qualifying_episodes"] == 0
    assert result.data["presence_total_minutes"] == 0.0
    assert result.data["presence_longest_minutes"] == 0.0


@pytest.mark.asyncio
async def test_room_dwell_history_empty_history():
    room = _FakeRoom(id=7, name="bathroom")
    db = _make_mock_db(room)
    person_location = _StubPersonLocationService(())
    services = ServiceContainer(db_factory=lambda: db, person_location=person_location)

    handler = PresenceQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json=_history_config()),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )

    assert result.data["presence_had_dwell"] is False
    assert result.data["presence_qualifying_episodes"] == 0


@pytest.mark.asyncio
async def test_room_dwell_history_unknown_room_fails_silent():
    db = _make_mock_db(None)
    person_location = _StubPersonLocationService(())
    services = ServiceContainer(db_factory=lambda: db, person_location=person_location)

    handler = PresenceQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json=_history_config(room_name="nonexistent")),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )

    assert result.success
    assert result.data["presence_had_dwell"] is False
    assert not person_location.calls


@pytest.mark.asyncio
async def test_room_dwell_history_no_person_location_service_fails_silent():
    room = _FakeRoom(id=7, name="bathroom")
    db = _make_mock_db(room)
    services = ServiceContainer(db_factory=lambda: db, person_location=None)

    handler = PresenceQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json=_history_config()),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )

    assert result.success
    assert result.data["presence_had_dwell"] is False


@pytest.mark.asyncio
async def test_room_dwell_history_missing_room_name_fails_silent():
    services = ServiceContainer(
        db_factory=lambda: _make_mock_db(None),
        person_location=_StubPersonLocationService(()),
    )

    handler = PresenceQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json=_history_config(room_name="")),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )

    assert result.success
    assert result.data["presence_had_dwell"] is False


@pytest.mark.asyncio
async def test_room_dwell_history_current_mode_still_default():
    """query_mode defaults to 'current'; existing behavior is unchanged."""
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM, room_name="kitchen")
    services = _make_services(_StubPresenceService(snapshot))
    handler = PresenceQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": "mom"}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )
    assert result.data["presence_available"] is True
    assert "presence_had_dwell" not in result.data
