from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from backend.services.guided_task.completion.activity import (
    ActivitySignalEvaluator,
    ZonePresenceEvaluator,
)


@dataclass
class _Session:
    id: int = 1
    person_id: str = "resident-1"


@dataclass
class _Step:
    zone_id: int | None = 7


@dataclass
class _Zone:
    id: int


class _Activity:
    async def query_in_window(self, **kwargs):
        self.kwargs = kwargs
        return [{"activity_type": kwargs["activity_type"]}]


async def test_activity_signal_complete_when_activity_in_window() -> None:
    activity = _Activity()
    evaluator = ActivitySignalEvaluator(
        activity_service=activity,
        gate_config={"activity": {"activity_type": "meal_prep", "window_minutes": 5}},
    )

    result = await evaluator.is_complete(
        session=_Session(),
        step=_Step(),
        evidence={"now": datetime(2026, 6, 17, 12, 0, tzinfo=UTC)},
    )

    assert result.complete is True
    assert activity.kwargs["activity_type"] == "meal_prep"


async def test_zone_presence_complete_when_in_target_zone() -> None:
    class _ZoneService:
        async def current_zone(self, person_id: str) -> _Zone:
            return _Zone(id=7)

    evaluator = ZonePresenceEvaluator(zone_service=_ZoneService(), gate_config={})

    result = await evaluator.is_complete(session=_Session(), step=_Step(zone_id=7), evidence={})

    assert result.complete is True


async def test_zone_presence_not_complete_when_elsewhere() -> None:
    class _ZoneService:
        async def current_zone(self, person_id: str) -> _Zone:
            return _Zone(id=8)

    evaluator = ZonePresenceEvaluator(zone_service=_ZoneService(), gate_config={})

    result = await evaluator.is_complete(session=_Session(), step=_Step(zone_id=7), evidence={})

    assert result.complete is False
