"""Unit tests for :class:`TrackingQueryHandler`.

Exercises the step's three main branches:
- unknown person (graceful no-op)
- current-room lookup with dwell computation
- condition evaluation (room/duration/signal match)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from backend.models.person import HouseholdMember, PersonLocationHistory, PersonLocationState
from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.tracking_query import TrackingQueryHandler


@dataclass
class _FakeExecution:
    id: int = 1


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)


def _make_trigger() -> TriggerContext:
    return TriggerContext(trigger_type="manual")


def _seed(db_factory, person_id: str, room: str, entered_minutes_ago: int) -> None:
    db = db_factory()
    try:
        if db.get(HouseholdMember, person_id) is None:
            db.add(HouseholdMember(id=person_id, name=person_id.title()))
        now = datetime.now(UTC) - timedelta(minutes=entered_minutes_ago)
        db.add(
            PersonLocationState(
                person_id=person_id,
                current_room_name=room,
                last_seen_at=now,
                last_sensor_id="cts",
                status="home",
                confidence=0.9,
            )
        )
        db.add(
            PersonLocationHistory(
                person_id=person_id,
                room_name=room,
                entered_at=now,
                source="cts",
            )
        )
        db.commit()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_unknown_person_gracefully_empty(db_factory):
    handler = TrackingQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": "nobody"}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=ServiceContainer(db_factory=db_factory),
    )
    assert result.success
    assert result.data["tracking_available"] is False
    assert result.data["tracking_satisfied"] is False
    assert result.data["tracking_signal_count"] == 0


@pytest.mark.asyncio
async def test_returns_current_room_and_dwell(db_factory):
    _seed(db_factory, "grandma", "bathroom", entered_minutes_ago=25)
    handler = TrackingQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={"person_id": "grandma"}),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=ServiceContainer(db_factory=db_factory),
    )
    data = result.data
    assert data["tracking_available"] is True
    assert data["tracking_room_name"] == "bathroom"
    assert data["tracking_dwell_minutes"] is not None
    assert data["tracking_dwell_minutes"] >= 24.0


@pytest.mark.asyncio
async def test_satisfied_when_room_and_duration_match(db_factory):
    _seed(db_factory, "grandma", "bathroom", entered_minutes_ago=25)
    handler = TrackingQueryHandler()
    result = await handler.execute(
        step=_FakeStep(
            config_json={
                "person_id": "grandma",
                "room": "bathroom",
                "duration_minutes": 20,
            }
        ),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=ServiceContainer(db_factory=db_factory),
    )
    assert result.data["tracking_satisfied"] is True


@pytest.mark.asyncio
async def test_not_satisfied_when_duration_below_threshold(db_factory):
    _seed(db_factory, "grandma", "bathroom", entered_minutes_ago=2)
    handler = TrackingQueryHandler()
    result = await handler.execute(
        step=_FakeStep(
            config_json={
                "person_id": "grandma",
                "room": "bathroom",
                "duration_minutes": 10,
            }
        ),
        execution=_FakeExecution(),
        pipeline_data={},
        trigger=_make_trigger(),
        services=ServiceContainer(db_factory=db_factory),
    )
    assert result.data["tracking_satisfied"] is False


@pytest.mark.asyncio
async def test_person_id_falls_back_to_pipeline_data(db_factory):
    _seed(db_factory, "grandma", "kitchen", entered_minutes_ago=5)
    handler = TrackingQueryHandler()
    result = await handler.execute(
        step=_FakeStep(config_json={}),
        execution=_FakeExecution(),
        pipeline_data={"persons": [{"id": "grandma"}]},
        trigger=_make_trigger(),
        services=ServiceContainer(db_factory=db_factory),
    )
    assert result.data["tracking_available"] is True
    assert result.data["tracking_person_id"] == "grandma"
