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
    calls: list[str] = field(default_factory=list)

    async def speak_step(self, *, session, step, rendered_prompt: str, is_retry: bool) -> None:
        self.calls.append(rendered_prompt)


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
            profile="watch",
        )

    async def run(self, gate_rule_id, profile, cameras, context):
        return self.verdict_to_return


def _seed_routine_with_watch(
    db_session,
    *,
    watch_enabled: bool = True,
    step_timeout_s: int = 100,
    resume_grace_s: int = 600,
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
                        "tick_s": 20,
                        "window_s": 4,
                        "max_frames": 3,
                    }
                },
                "mode": "all",
            },
            is_safety_critical=False,
        )
    )
    db_session.commit()
    return routine.id


def _settings(step_timeout_s: int = 100, resume_grace_s: int = 600) -> Settings:
    return Settings.from_dict(
        {
            "app": {"timezone": "America/New_York"},
            "guided_task": {
                "step_timeout_s": step_timeout_s,
                "max_step_attempts": 3,
                "resume_grace_s": resume_grace_s,
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
                    }
                },
            },
        }
    )


@pytest.mark.asyncio
async def test_progress_verdict_defers_reprompt(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera
    monkeypatch.setattr(
        "backend.services.guided_task.camera_selection.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner()
    # Mocking positive complete watch verdict (progress seen)
    gate_runner.verdict_to_return = GateVerdict(
        complete=True,
        confidence=0.8,
        reason="in_progress",
        node_results={},
        cost={},
        profile="watch",
    )
    voice = _RecordingVoice()

    routine_id = _seed_routine_with_watch(db_session, watch_enabled=True, step_timeout_s=100)
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=voice,
        escalator=_RecordingEscalator(),
        settings=_settings(step_timeout_s=100),
        time_fn=clock,
        gate_runner=gate_runner,
    )
    session = await svc.start(routine_id, "resident-1")

    # Run watch once so progress is seen
    await svc.tick(clock.now)
    assert (session.id, 0) in svc._progress_seen_at

    voice.calls.clear()

    # Advance clock close to the step timeout (90s, less than 100s)
    clock.advance(90)
    decision = await svc.on_step_timeout(session.id)

    # Re-prompt should be deferred: decision.kind should be "noop" (nag suppressed)
    assert decision.kind == "noop"
    assert decision.reason == "nag_suppressed"
    assert len(voice.calls) == 0  # no reprompt spoken!


@pytest.mark.asyncio
async def test_no_progress_does_not_suppress(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera
    monkeypatch.setattr(
        "backend.services.guided_task.camera_selection.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner()
    # Watch verdict shows incomplete (no progress seen)
    gate_runner.verdict_to_return = GateVerdict(
        complete=False,
        confidence=0.3,
        reason="not_done",
        node_results={},
        cost={},
        profile="watch",
    )
    voice = _RecordingVoice()

    routine_id = _seed_routine_with_watch(db_session, watch_enabled=True, step_timeout_s=100)
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=voice,
        escalator=_RecordingEscalator(),
        settings=_settings(step_timeout_s=100),
        time_fn=clock,
        gate_runner=gate_runner,
    )
    session = await svc.start(routine_id, "resident-1")

    # Run watch once -> complete is False -> no progress seen
    await svc.tick(clock.now)
    assert (session.id, 0) not in svc._progress_seen_at

    voice.calls.clear()

    clock.advance(110)  # beyond timeout
    decision = await svc.on_step_timeout(session.id)

    # Should not be suppressed -> decision.kind == "retry"
    assert decision.kind == "retry"
    assert len(voice.calls) > 0  # reprompt spoken!


@pytest.mark.asyncio
async def test_suppression_does_not_block_abandonment(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera
    monkeypatch.setattr(
        "backend.services.guided_task.camera_selection.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner()
    # Progress is seen
    gate_runner.verdict_to_return = GateVerdict(
        complete=True,
        confidence=0.8,
        reason="in_progress",
        node_results={},
        cost={},
        profile="watch",
    )

    routine_id = _seed_routine_with_watch(db_session, watch_enabled=True, step_timeout_s=100, resume_grace_s=600)
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=_RecordingVoice(),
        escalator=_RecordingEscalator(),
        settings=_settings(step_timeout_s=100, resume_grace_s=600),
        time_fn=clock,
        gate_runner=gate_runner,
    )
    session = await svc.start(routine_id, "resident-1")

    # Run watch -> progress seen
    await svc.tick(clock.now)

    # Advance clock past resume_grace_s (650s)
    clock.advance(650)

    # Tick should run abandonment check and transition session to abandoned
    await svc.tick(clock.now)

    db_session.expire_all()
    session = svc._store.get_session(session.id)
    assert session.status == "abandoned"
