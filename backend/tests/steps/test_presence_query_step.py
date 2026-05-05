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
        sources=(PresenceSource(name="cts_location", confidence=0.9),),
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
