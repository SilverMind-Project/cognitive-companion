"""Unit tests for :class:`HomeStateHandler`.

Exercises four cases, one per presence status:
- present_room → at_home=true
- asleep → asleep=true
- away → away=true
- unknown → state_unknown=true
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from backend.services.presence import PresenceSnapshot, PresenceStatus
from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.home_state import HomeStateHandler


@dataclass
class _FakeExecution:
    id: int = 1


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)


def _make_trigger() -> TriggerContext:
    return TriggerContext(trigger_type="manual")


def _make_snapshot(status: PresenceStatus) -> PresenceSnapshot:
    return PresenceSnapshot(
        person_id="mom",
        status=status,
        room_id="k1",
        room_name="kitchen",
        confidence=0.9,
        last_seen_at=datetime.now(UTC),
        dwell_minutes=5.0,
        sources=(),
        inferred_at=datetime.now(UTC),
    )


class _StubPresenceService:
    def __init__(self, snapshot: PresenceSnapshot) -> None:
        self.snapshot = snapshot

    async def get(self, person_id: str, *, at=None):
        return self.snapshot


@pytest.mark.asyncio
async def test_present_room():
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM)
    services = ServiceContainer(db_factory=lambda: None, presence=_StubPresenceService(snapshot))
    handler = HomeStateHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": "mom"}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )
    data = result.data
    assert data["home_at_home"] is True
    assert data["home_asleep"] is False
    assert data["home_away"] is False
    assert data["home_state_unknown"] is False


@pytest.mark.asyncio
async def test_asleep():
    snapshot = _make_snapshot(PresenceStatus.ASLEEP)
    services = ServiceContainer(db_factory=lambda: None, presence=_StubPresenceService(snapshot))
    handler = HomeStateHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": "mom"}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )
    data = result.data
    assert data["home_at_home"] is True
    assert data["home_asleep"] is True
    assert data["home_away"] is False


@pytest.mark.asyncio
async def test_away():
    snapshot = _make_snapshot(PresenceStatus.AWAY)
    services = ServiceContainer(db_factory=lambda: None, presence=_StubPresenceService(snapshot))
    handler = HomeStateHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": "mom"}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )
    data = result.data
    assert data["home_at_home"] is False
    assert data["home_asleep"] is False
    assert data["home_away"] is True


@pytest.mark.asyncio
async def test_unknown():
    snapshot = _make_snapshot(PresenceStatus.UNKNOWN)
    services = ServiceContainer(db_factory=lambda: None, presence=_StubPresenceService(snapshot))
    handler = HomeStateHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": "mom"}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )
    data = result.data
    assert data["home_at_home"] is False
    assert data["home_asleep"] is False
    assert data["home_away"] is False
    assert data["home_state_unknown"] is True


@pytest.mark.asyncio
async def test_custom_output_key():
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM)
    services = ServiceContainer(db_factory=lambda: None, presence=_StubPresenceService(snapshot))
    handler = HomeStateHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": "mom", "output_key": "loc"}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=services,
    )
    data = result.data
    assert data["loc_at_home"] is True
    assert data["loc_asleep"] is False
    assert data["loc_away"] is False
    assert data["loc_state_unknown"] is False


@pytest.mark.asyncio
async def test_no_presence_service():
    handler = HomeStateHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": "mom"}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=ServiceContainer(db_factory=lambda: None),
    )
    data = result.data
    assert data["home_at_home"] is False
    assert data["home_state_unknown"] is True
