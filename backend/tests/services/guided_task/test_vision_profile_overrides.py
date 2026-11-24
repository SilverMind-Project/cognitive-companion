"""Per-profile vision overrides reach the camera cascade and the gate profile."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from backend.core.config import Settings
from backend.models.guided_task import Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.guided_task.camera_selection import ResolvedCamera
from backend.services.guided_task.completion.vision import VisionEvaluator
from backend.services.guided_task.gate_runner import GateVerdict, _CoolOffCache
from backend.services.guided_task.service import GuidedTaskService

_GLOBAL_VISION = {
    "max_cameras": 3,
    "confirm": {"min_confidence": 0.7},
    "watch": {"enabled": False, "tick_s": 20, "min_confidence": 0.6},
}


class _Runner:
    def __init__(self) -> None:
        self.cache = _CoolOffCache()
        self.profiles: list = []
        self._time_fn = lambda: datetime.now(UTC)

    async def run(self, gate_rule_id, profile, cameras, context):
        self.profiles.append(profile)
        return GateVerdict(
            complete=False,
            confidence=0.2,
            reason="not_done",
            node_results={},
            cost={},
            profile=profile.name,
        )


@dataclass
class _Session:
    id: int = 1
    person_id: str = "resident-1"


@dataclass
class _Step:
    ord: int = 0
    camera_ids: list[str] | None = None
    zone_id: int | None = None


@dataclass
class _Voice:
    async def speak_step(self, *, session, step, rendered_prompt: str, is_retry: bool) -> None:
        return None


class _NoSafety:
    async def evaluate(self, *, session):
        return []


def _cascade(monkeypatch, target: str) -> AsyncMock:
    mock = AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")])
    monkeypatch.setattr(target, mock)
    return mock


async def test_confirm_profile_max_cameras_overrides_global(monkeypatch) -> None:
    cascade = _cascade(
        monkeypatch, "backend.services.guided_task.completion.vision.select_cameras_tagged"
    )
    evaluator = VisionEvaluator(
        gate_config={"vision": {"gate_graph_rule_id": 42, "confirm": {"max_cameras": 1}}},
        gate_runner=_Runner(),
        settings=Settings.from_dict({"guided_task": {"vision": _GLOBAL_VISION}}),
    )
    await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})
    assert cascade.call_args.kwargs["max_cameras"] == 1


@pytest.mark.asyncio
async def test_watch_profile_max_cameras_and_min_confidence_override_global(
    db_session, monkeypatch
) -> None:
    cascade = _cascade(
        monkeypatch, "backend.services.guided_task.camera_selection.select_cameras_tagged"
    )
    if db_session.get(HouseholdMember, "resident-1") is None:
        db_session.add(HouseholdMember(id="resident-1", name="Resident"))
        db_session.flush()
    routine = Routine(name="Make tea", person_id="resident-1", is_enabled=True)
    db_session.add(routine)
    db_session.flush()
    db_session.add(
        RoutineStep(
            routine_id=routine.id,
            ord=0,
            prompt_template="Boil water",
            completion_gate={
                "vision": {
                    "gate_graph_rule_id": 42,
                    "watch": {"enabled": True, "max_cameras": 2, "min_confidence": 0.9},
                }
            },
        )
    )
    db_session.commit()

    now = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
    runner = _Runner()
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=_Voice(),
        settings=Settings.from_dict(
            {
                "guided_task": {
                    "step_timeout_s": 300,
                    "max_step_attempts": 3,
                    "resume_grace_s": 600,
                    "vision": _GLOBAL_VISION,
                }
            }
        ),
        time_fn=lambda: now,
        gate_runner=runner,
        safety_watch=_NoSafety(),
    )
    await svc.start(routine.id, "resident-1")
    await svc.tick(now + timedelta(seconds=1))

    assert cascade.call_args.kwargs["max_cameras"] == 2
    assert runner.profiles[-1].min_confidence == 0.9
