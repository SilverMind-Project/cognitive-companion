"""G1/G3 fix: vision-confirm is an always-run verifier, not a competing gate.

These tests prove the editor-default completion_gate config (``kinds:
["response", "vision_confirm"]``, no ``mode`` key) actually runs the vision
gate on the resident's "done", holds on a negative verdict, and reaches the
bounded-disagreement escape hatch, per
``codebase-hardening-m23-cc-completion-gate-semantics.md``.
"""

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
        self.now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)

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
    def __init__(self, verdict: GateVerdict) -> None:
        from backend.services.guided_task.gate_runner import _CoolOffCache

        self.cache = _CoolOffCache()
        self._time_fn = lambda: datetime.now(UTC)
        self.run_count = 0
        self.verdict_to_return = verdict

    async def run(self, gate_rule_id, profile, cameras, context):
        self.run_count += 1
        return self.verdict_to_return


class _FakeActivityService:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def query_in_window(self, **kwargs):
        return self._rows


def _seed_routine(
    db_session,
    *,
    kinds: list[str],
    mode: str | None,
    extra_gate: dict | None = None,
) -> int:
    member = db_session.get(HouseholdMember, "resident-1")
    if not member:
        db_session.add(HouseholdMember(id="resident-1", name="Resident"))
        db_session.flush()

    routine = Routine(name="Make tea", person_id="resident-1", is_enabled=True)
    db_session.add(routine)
    db_session.flush()

    gate: dict = {"kinds": kinds}
    if mode is not None:
        gate["mode"] = mode
    if extra_gate:
        gate.update(extra_gate)

    db_session.add(
        RoutineStep(
            routine_id=routine.id,
            ord=0,
            prompt_template="Step 0",
            completion_gate=gate,
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


def _settings() -> Settings:
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
                        "max_disagreements": 2,
                        "window_s": 20,
                        "max_frames": 9,
                        "min_confidence": 0.7,
                        "min_interval_s": 15,
                    }
                },
            },
        }
    )


def _service(db_session, clock, gate_runner, settings_obj, *, activity_service=None):
    return GuidedTaskService(
        db_factory=lambda: db_session,
        voice=_RecordingVoice(),
        escalator=_RecordingEscalator(),
        settings=settings_obj,
        time_fn=clock,
        gate_runner=gate_runner,
        activity_service=activity_service,
    )


@pytest.mark.asyncio
async def test_default_editor_config_runs_vision_on_done(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner(
        GateVerdict(
            complete=False,
            confidence=0.3,
            reason="not_done",
            node_results={},
            cost={},
            profile="confirm",
        )
    )
    routine_id = _seed_routine(
        db_session,
        kinds=["response", "vision_confirm"],
        mode=None,
        extra_gate={"vision": {"gate_graph_rule_id": 42, "confirm": {}}},
    )
    svc = _service(db_session, clock, gate_runner, _settings())

    session = await svc.request_start(routine_id, "resident-1")

    res = await svc.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    assert gate_runner.run_count == 1
    assert res["advanced"] is False

    stmt = select(GuidedSessionEvent).where(
        GuidedSessionEvent.session_id == session.id,
        GuidedSessionEvent.kind == "vision_confirm",
    )
    events = list(db_session.execute(stmt).scalars().all())
    assert len(events) == 1
    assert events[0].detail["complete"] is False

    db_session.expire_all()
    reloaded = svc._store.get_session(session.id)
    assert reloaded.current_step_ord == 0


@pytest.mark.asyncio
async def test_default_config_advances_on_positive_verdict(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner(
        GateVerdict(
            complete=True,
            confidence=0.9,
            reason="done",
            node_results={},
            cost={},
            profile="confirm",
        )
    )
    routine_id = _seed_routine(
        db_session,
        kinds=["response", "vision_confirm"],
        mode=None,
        extra_gate={"vision": {"gate_graph_rule_id": 42, "confirm": {}}},
    )
    svc = _service(db_session, clock, gate_runner, _settings())

    session = await svc.request_start(routine_id, "resident-1")
    res = await svc.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    assert gate_runner.run_count == 1
    assert res["advanced"] is True


@pytest.mark.asyncio
async def test_bounded_disagreement_reachable_in_default_config(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner(
        GateVerdict(
            complete=False,
            confidence=0.3,
            reason="not_done",
            node_results={},
            cost={},
            profile="confirm",
        )
    )
    routine_id = _seed_routine(
        db_session,
        kinds=["response", "vision_confirm"],
        mode=None,
        extra_gate={"vision": {"gate_graph_rule_id": 42, "confirm": {}}},
    )
    svc = _service(db_session, clock, gate_runner, _settings())

    session = await svc.request_start(routine_id, "resident-1")

    res1 = await svc.handle_completion(session.id, {"confirmed": True, "step_ord": 0})
    assert res1["advanced"] is False

    clock.advance(20)

    res2 = await svc.handle_completion(session.id, {"confirmed": True, "step_ord": 0})
    assert res2["advanced"] is True

    stmt = select(GuidedSessionEvent).where(
        GuidedSessionEvent.session_id == session.id,
        GuidedSessionEvent.kind == "vision_deferred",
    )
    events = list(db_session.execute(stmt).scalars().all())
    assert len(events) == 1
    assert events[0].detail["action"] == "advance"


@pytest.mark.asyncio
async def test_mode_any_assists_advisory(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner(
        GateVerdict(
            complete=True,
            confidence=0.9,
            reason="done",
            node_results={},
            cost={},
            profile="confirm",
        )
    )
    routine_id = _seed_routine(
        db_session,
        kinds=["response", "vision_confirm", "activity_signal"],
        mode="any",
        extra_gate={
            "vision": {"gate_graph_rule_id": 42, "confirm": {}},
            "activity": {"activity_type": "meal_prep", "window_minutes": 5},
        },
    )
    svc = _service(
        db_session, clock, gate_runner, _settings(), activity_service=_FakeActivityService([])
    )

    session = await svc.request_start(routine_id, "resident-1")
    res = await svc.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    # Activity assist failed (no rows), but "any" mode makes it advisory: still advances.
    assert res["advanced"] is True


@pytest.mark.asyncio
async def test_mode_all_assists_required(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner(
        GateVerdict(
            complete=True,
            confidence=0.9,
            reason="done",
            node_results={},
            cost={},
            profile="confirm",
        )
    )
    routine_id = _seed_routine(
        db_session,
        kinds=["response", "vision_confirm", "activity_signal"],
        mode="all",
        extra_gate={
            "vision": {"gate_graph_rule_id": 42, "confirm": {}},
            "activity": {"activity_type": "meal_prep", "window_minutes": 5},
        },
    )
    svc = _service(
        db_session, clock, gate_runner, _settings(), activity_service=_FakeActivityService([])
    )

    session = await svc.request_start(routine_id, "resident-1")
    res = await svc.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    # Activity assist failed and "all" mode requires every assist: does not advance.
    assert res["advanced"] is False


@pytest.mark.asyncio
async def test_unconfirmed_done_still_rejected(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner(
        GateVerdict(
            complete=True,
            confidence=0.9,
            reason="done",
            node_results={},
            cost={},
            profile="confirm",
        )
    )
    routine_id = _seed_routine(
        db_session,
        kinds=["response", "vision_confirm"],
        mode=None,
        extra_gate={"vision": {"gate_graph_rule_id": 42, "confirm": {}}},
    )
    svc = _service(db_session, clock, gate_runner, _settings())

    session = await svc.request_start(routine_id, "resident-1")
    res = await svc.handle_completion(session.id, {"confirmed": False, "step_ord": 0})

    assert gate_runner.run_count == 0
    assert res["advanced"] is False
    assert res["reason"] == "not_confirmed"
