from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from backend.core.config import Settings
from backend.models.guided_task import Routine, RoutineStep
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
        self.run_count = 0
        self.verdict_to_return = GateVerdict(
            complete=False,
            confidence=0.3,
            reason="not_done",
            node_results={},
            cost={"model_calls": 1, "frames": 2, "latency_ms": 100},
            profile="watch",
        )

    async def run(self, gate_rule_id, profile, cameras, context):
        self.run_count += 1
        return self.verdict_to_return


class FailingGateGraphRunner:
    def __init__(self):
        from backend.services.guided_task.gate_runner import _CoolOffCache

        self.cache = _CoolOffCache()
        self._time_fn = lambda: datetime.now(UTC)

    async def run(self, gate_rule_id, profile, cameras, context):
        raise ValueError("Failed on purpose")


class FakeSafetyWatch:
    def __init__(self):
        self.evaluated = False

    async def evaluate(self, *, session):
        self.evaluated = True
        return []


def _seed_routine_with_watch(
    db_session,
    *,
    watch_enabled: bool = True,
    tick_s: int = 20,
) -> int:
    member = db_session.get(HouseholdMember, "resident-1")
    if not member:
        db_session.add(HouseholdMember(id="resident-1", name="Resident"))
        db_session.flush()

    routine = Routine(name="Make tea", person_id="resident-1", is_enabled=True)
    db_session.add(routine)
    db_session.flush()

    db_session.add(
        RoutineStep(
            routine_id=routine.id,
            ord=0,
            prompt_template="Step 0 with watch check",
            completion_gate={
                "kinds": ["response", "vision_confirm"],
                "vision": {
                    "gate_graph_rule_id": 42,
                    "watch": {
                        "enabled": watch_enabled,
                        "tick_s": tick_s,
                        "window_s": 4,
                        "max_frames": 3,
                    },
                },
                "mode": "all",
            },
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
                    },
                    "watch": {
                        "enabled": False,
                        "tick_s": 20,
                        "window_s": 4,
                        "max_frames": 3,
                    },
                },
            },
        }
    )


@pytest.mark.asyncio
async def test_watch_runs_only_when_enabled(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.camera_selection.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner()
    safety = FakeSafetyWatch()

    # 1. Disabled watch
    routine_id = _seed_routine_with_watch(db_session, watch_enabled=False)
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=_RecordingVoice(),
        escalator=_RecordingEscalator(),
        settings=_settings(),
        time_fn=clock,
        gate_runner=gate_runner,
        safety_watch=safety,
    )
    await svc.start(routine_id, "resident-1")

    await svc.tick(clock.now)
    assert gate_runner.run_count == 0
    assert safety.evaluated is True


@pytest.mark.asyncio
async def test_watch_throttled_by_tick_s(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.camera_selection.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner()
    safety = FakeSafetyWatch()

    routine_id = _seed_routine_with_watch(db_session, watch_enabled=True, tick_s=20)
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=_RecordingVoice(),
        escalator=_RecordingEscalator(),
        settings=_settings(),
        time_fn=clock,
        gate_runner=gate_runner,
        safety_watch=safety,
    )
    await svc.start(routine_id, "resident-1")

    # Tick 1: runs watch
    await svc.tick(clock.now)
    assert gate_runner.run_count == 1

    # Tick 2: within tick_s (10s later) -> skipped
    clock.advance(10)
    await svc.tick(clock.now)
    assert gate_runner.run_count == 1

    # Tick 3: after tick_s (15s later, total 25s) -> runs again
    clock.advance(15)
    await svc.tick(clock.now)
    assert gate_runner.run_count == 2


@pytest.mark.asyncio
async def test_watch_emits_event_and_warms_cache(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.camera_selection.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner()
    safety = FakeSafetyWatch()

    routine_id = _seed_routine_with_watch(db_session, watch_enabled=True)
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=_RecordingVoice(),
        escalator=_RecordingEscalator(),
        settings=_settings(),
        time_fn=clock,
        gate_runner=gate_runner,
        safety_watch=safety,
    )
    session = await svc.start(routine_id, "resident-1")

    await svc.tick(clock.now)

    # Check cache has both keys warmed
    assert (
        gate_runner.cache.get_fresh((str(session.id), 0, "watch"), min_interval_s=15, now=clock.now)
        is not None
    )
    assert (
        gate_runner.cache.get_fresh(
            (str(session.id), 0, "confirm"), min_interval_s=15, now=clock.now
        )
        is not None
    )

    # Check event was written
    events = svc._store.list_events(session_id=session.id)
    watch_event = next((e for e in events if e.kind == "watch"), None)
    assert watch_event is not None
    assert watch_event.detail["profile"] == "watch"
    assert watch_event.detail["complete"] is False


@pytest.mark.asyncio
async def test_watch_does_not_change_step_state(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.camera_selection.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner()
    gate_runner.verdict_to_return = GateVerdict(
        complete=True,
        confidence=0.9,
        reason="done",
        node_results={},
        cost={},
        profile="watch",
    )
    safety = FakeSafetyWatch()

    # auto_advance is False by default
    routine_id = _seed_routine_with_watch(db_session, watch_enabled=True)
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=_RecordingVoice(),
        escalator=_RecordingEscalator(),
        settings=_settings(),
        time_fn=clock,
        gate_runner=gate_runner,
        safety_watch=safety,
    )
    session = await svc.start(routine_id, "resident-1")

    await svc.tick(clock.now)

    db_session.expire_all()
    session = svc._store.get_session(session.id)
    assert session.current_step_ord == 0  # didn't change status or step!


@pytest.mark.asyncio
async def test_watch_error_isolated_from_safety_watch(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.camera_selection.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FailingGateGraphRunner()
    safety = FakeSafetyWatch()

    routine_id = _seed_routine_with_watch(db_session, watch_enabled=True)
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=_RecordingVoice(),
        escalator=_RecordingEscalator(),
        settings=_settings(),
        time_fn=clock,
        gate_runner=gate_runner,
        safety_watch=safety,
    )
    await svc.start(routine_id, "resident-1")

    # Should not throw exception, and safety should still run
    await svc.tick(clock.now)
    assert safety.evaluated is True
