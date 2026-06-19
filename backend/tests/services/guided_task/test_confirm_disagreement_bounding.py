from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from backend.core.config import Settings
from backend.models.guided_task import GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.guided_task.gate_runner import GateVerdict
from backend.services.guided_task.service import GuidedTaskService


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)

    def __call__(self) -> datetime:
        return self.now


@dataclass
class _RecordingVoice:
    async def speak_step(self, *, session, step, rendered_prompt: str, is_retry: bool) -> None:
        pass


@dataclass
class _RecordingEscalator:
    calls: list[tuple[int, str, bool]] = field(default_factory=list)

    async def escalate(self, *, session, reason: str, emergency: bool) -> None:
        self.calls.append((session.id, reason, emergency))


class FakeGateGraphRunner:
    def __init__(self):
        from backend.services.guided_task.gate_runner import _CoolOffCache

        self.cache = _CoolOffCache()
        self._time_fn = lambda: datetime.now(UTC)
        self.verdict_to_return = GateVerdict(
            complete=False,
            confidence=0.3,
            reason="not_done",
            node_results={},
            cost={},
            profile="confirm",
        )

    async def run(self, gate_rule_id, profile, cameras, context):
        return self.verdict_to_return


def _seed_routine_with_vision(
    db_session,
    *,
    max_disagreements: int | None = None,
    on_max_disagreements: str | None = None,
) -> int:
    member = db_session.get(HouseholdMember, "resident-1")
    if not member:
        db_session.add(HouseholdMember(id="resident-1", name="Resident"))
        db_session.flush()

    routine = Routine(name="Make tea", person_id="resident-1", is_enabled=True)
    db_session.add(routine)
    db_session.flush()

    vision_confirm_cfg = {"gate_graph_rule_id": 42, "confirm": {}}
    if max_disagreements is not None:
        vision_confirm_cfg["confirm"]["max_disagreements"] = max_disagreements
    if on_max_disagreements is not None:
        vision_confirm_cfg["confirm"]["on_max_disagreements"] = on_max_disagreements

    db_session.add(
        RoutineStep(
            routine_id=routine.id,
            ord=0,
            prompt_template="Step 0 with vision check",
            completion_gate={
                "kinds": ["response", "vision_confirm"],
                "vision": vision_confirm_cfg,
                "mode": "all",
            },
            is_safety_critical=False,
        )
    )
    db_session.add(
        RoutineStep(
            routine_id=routine.id,
            ord=1,
            prompt_template="Step 1 final step",
            completion_gate={"kinds": ["response"]},
            is_safety_critical=False,
        )
    )
    db_session.commit()
    return routine.id


def _settings(max_disagreements: int = 2) -> Settings:
    return Settings.from_dict(
        {
            "app": {"timezone": "America/New_York"},
            "guided_task": {
                "step_timeout_s": 300,
                "max_step_attempts": 3,
                "resume_grace_s": 600,
                "transcript_retention_days": 30,
                "summon_channels": ["ha_speaker_tts", "pwa_popup_text"],
                "vision": {
                    "confirm": {
                        "max_disagreements": max_disagreements,
                        "window_s": 20,
                        "max_frames": 9,
                        "min_confidence": 0.7,
                        "min_interval_s": 15,
                    }
                },
            },
        }
    )


def _service(
    db_session,
    clock: _Clock,
    gate_runner,
    escalator,
    settings_obj,
) -> GuidedTaskService:
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=_RecordingVoice(),
        escalator=escalator,
        settings=settings_obj,
        time_fn=clock,
        gate_runner=gate_runner,
    )
    return svc


@pytest.mark.asyncio
async def test_first_disagreement_returns_wait(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner()
    escalator = _RecordingEscalator()
    settings_obj = _settings(max_disagreements=2)

    routine_id = _seed_routine_with_vision(db_session)
    svc = _service(db_session, clock, gate_runner, escalator, settings_obj)

    session = await svc.request_start(routine_id, "resident-1")

    # Call completion asserting she is done (confirmed=True) but VLM says not complete
    res = await svc.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    # First disagreement: should return wait
    assert res["advanced"] is False
    assert res["reason"] == "not_done"


@pytest.mark.asyncio
async def test_reaching_max_disagreements_advances_deferred(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner()
    escalator = _RecordingEscalator()
    settings_obj = _settings(max_disagreements=2)

    routine_id = _seed_routine_with_vision(db_session)
    svc = _service(db_session, clock, gate_runner, escalator, settings_obj)

    session = await svc.request_start(routine_id, "resident-1")

    # First disagreement
    res1 = await svc.handle_completion(session.id, {"confirmed": True, "step_ord": 0})
    assert res1["advanced"] is False

    clock.advance(20)

    # Second disagreement: matches max_disagreements = 2, so should defer (advance)
    res2 = await svc.handle_completion(session.id, {"confirmed": True, "step_ord": 0})
    assert res2["advanced"] is True

    # Assert event list contains "vision_deferred" kind and right details
    stmt = select(GuidedSessionEvent).where(
        GuidedSessionEvent.session_id == session.id, GuidedSessionEvent.kind == "vision_deferred"
    )
    events = list(db_session.execute(stmt).scalars().all())
    assert len(events) == 1
    assert events[0].detail["completion_reason"] == "vision_deferred_to_response"
    assert events[0].detail["disagreements"] == 2
    assert events[0].detail["action"] == "advance"


@pytest.mark.asyncio
async def test_on_max_disagreements_escalate_option(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner()
    escalator = _RecordingEscalator()
    settings_obj = _settings(max_disagreements=2)

    routine_id = _seed_routine_with_vision(
        db_session, max_disagreements=2, on_max_disagreements="escalate"
    )
    svc = _service(db_session, clock, gate_runner, escalator, settings_obj)

    session = await svc.request_start(routine_id, "resident-1")

    # First disagreement
    res1 = await svc.handle_completion(session.id, {"confirmed": True, "step_ord": 0})
    assert res1["advanced"] is False

    clock.advance(20)

    # Second disagreement: should escalate
    res2 = await svc.handle_completion(session.id, {"confirmed": True, "step_ord": 0})
    assert res2["advanced"] is False
    assert escalator.calls == [(session.id, "vision_disagreement_escalation", False)]

    # Assert event list contains "vision_deferred" kind with right detail
    stmt = select(GuidedSessionEvent).where(
        GuidedSessionEvent.session_id == session.id, GuidedSessionEvent.kind == "vision_deferred"
    )
    events = list(db_session.execute(stmt).scalars().all())
    assert len(events) == 1
    assert events[0].detail["action"] == "escalate"


@pytest.mark.asyncio
async def test_disagreement_count_is_durable(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner()
    escalator = _RecordingEscalator()
    settings_obj = _settings(max_disagreements=2)

    routine_id = _seed_routine_with_vision(db_session)
    svc = _service(db_session, clock, gate_runner, escalator, settings_obj)

    session = await svc.request_start(routine_id, "resident-1")

    # Record first disagreement event
    await svc.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    clock.advance(20)

    # Clear/reload service or session by recreating service layer (simulate reload)
    svc2 = _service(db_session, clock, gate_runner, escalator, settings_obj)

    # Second disagreement: should still trigger advance because it's stored in DB!
    res2 = await svc2.handle_completion(session.id, {"confirmed": True, "step_ord": 0})
    assert res2["advanced"] is True
