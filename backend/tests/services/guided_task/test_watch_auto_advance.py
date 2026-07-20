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
from backend.services.knowledge.voice_instructions import VoiceInstructionConfig

_AUTO_ADVANCE_PREFIX = (
    "Acknowledge warmly that you can see the step is done, then give the next instruction."
)


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
            complete=True,
            confidence=0.9,
            reason="done",
            node_results={},
            cost={},
            profile="watch",
        )

    async def run(self, gate_rule_id, profile, cameras, context):
        return self.verdict_to_return


def _seed_routine_with_auto_advance(
    db_session,
    *,
    auto_advance: bool = True,
    auto_advance_k: int = 3,
    is_safety_critical: bool = False,
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
            prompt_template="Step 0 prompt template",
            completion_gate={
                "kinds": ["response", "vision_confirm"],
                "vision": {
                    "gate_graph_rule_id": 42,
                    "watch": {
                        "enabled": True,
                        "tick_s": 20,
                        "window_s": 4,
                        "max_frames": 3,
                        "auto_advance": auto_advance,
                        "auto_advance_k": auto_advance_k,
                    },
                },
                "mode": "all",
            },
            is_safety_critical=is_safety_critical,
        )
    )
    db_session.add(
        RoutineStep(
            routine_id=routine.id,
            ord=1,
            prompt_template="Step 1 prompt template",
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
                    },
                    "watch": {
                        "enabled": False,
                        "tick_s": 20,
                        "window_s": 4,
                        "max_frames": 3,
                        "auto_advance": False,
                        "auto_advance_k": 3,
                    },
                },
            },
        }
    )


@pytest.mark.asyncio
async def test_k_consecutive_completes_advances(db_session, monkeypatch) -> None:
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
    voice = _RecordingVoice()

    routine_id = _seed_routine_with_auto_advance(db_session, auto_advance=True, auto_advance_k=3)
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=voice,
        escalator=_RecordingEscalator(),
        settings=_settings(),
        time_fn=clock,
        gate_runner=gate_runner,
        voice_instructions=VoiceInstructionConfig(
            guided_task_auto_advance_prefix=_AUTO_ADVANCE_PREFIX
        ),
    )
    session = await svc.start(routine_id, "resident-1")

    # Watch 1
    await svc.tick(clock.now)
    db_session.expire_all()
    session = svc._store.get_session(session.id)
    assert session.current_step_ord == 0

    # Watch 2
    clock.advance(25)
    await svc.tick(clock.now)
    db_session.expire_all()
    session = svc._store.get_session(session.id)
    assert session.current_step_ord == 0

    # Watch 3: streak met (3 consecutive complete/high conf) -> auto-advances
    clock.advance(25)
    await svc.tick(clock.now)
    db_session.expire_all()
    session = svc._store.get_session(session.id)
    assert session.current_step_ord == 1

    # Check spoken warm transition
    assert (
        len(voice.calls) == 2
    )  # first call was step 0 start, second was step 1 enter (with prefix)
    assert _AUTO_ADVANCE_PREFIX in voice.calls[1]


@pytest.mark.asyncio
async def test_streak_resets_on_low_confidence(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.camera_selection.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner()
    voice = _RecordingVoice()

    routine_id = _seed_routine_with_auto_advance(db_session, auto_advance=True, auto_advance_k=3)
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=voice,
        escalator=_RecordingEscalator(),
        settings=_settings(),
        time_fn=clock,
        gate_runner=gate_runner,
    )
    session = await svc.start(routine_id, "resident-1")

    # Watch 1: complete=True, conf=0.9
    gate_runner.verdict_to_return = GateVerdict(
        complete=True, confidence=0.9, reason="done", node_results={}, cost={}, profile="watch"
    )
    await svc.tick(clock.now)

    # Watch 2: complete=True, conf=0.5 (low confidence) -> resets streak
    clock.advance(25)
    gate_runner.verdict_to_return = GateVerdict(
        complete=True, confidence=0.5, reason="unsure", node_results={}, cost={}, profile="watch"
    )
    await svc.tick(clock.now)

    # Watch 3: complete=True, conf=0.9 -> streak is 1
    clock.advance(25)
    gate_runner.verdict_to_return = GateVerdict(
        complete=True, confidence=0.9, reason="done", node_results={}, cost={}, profile="watch"
    )
    await svc.tick(clock.now)

    db_session.expire_all()
    session = svc._store.get_session(session.id)
    assert session.current_step_ord == 0  # not advanced because streak reset


@pytest.mark.asyncio
async def test_streak_resets_on_incomplete(db_session, monkeypatch) -> None:
    from backend.services.guided_task.camera_selection import ResolvedCamera

    monkeypatch.setattr(
        "backend.services.guided_task.camera_selection.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    clock = _Clock()
    gate_runner = FakeGateGraphRunner()
    voice = _RecordingVoice()

    routine_id = _seed_routine_with_auto_advance(db_session, auto_advance=True, auto_advance_k=3)
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=voice,
        escalator=_RecordingEscalator(),
        settings=_settings(),
        time_fn=clock,
        gate_runner=gate_runner,
    )
    session = await svc.start(routine_id, "resident-1")

    # Watch 1: complete=True, conf=0.9
    gate_runner.verdict_to_return = GateVerdict(
        complete=True, confidence=0.9, reason="done", node_results={}, cost={}, profile="watch"
    )
    await svc.tick(clock.now)

    # Watch 2: complete=False -> resets streak
    clock.advance(25)
    gate_runner.verdict_to_return = GateVerdict(
        complete=False, confidence=0.8, reason="not_done", node_results={}, cost={}, profile="watch"
    )
    await svc.tick(clock.now)

    # Watch 3: complete=True, conf=0.9 -> streak is 1
    clock.advance(25)
    gate_runner.verdict_to_return = GateVerdict(
        complete=True, confidence=0.9, reason="done", node_results={}, cost={}, profile="watch"
    )
    await svc.tick(clock.now)

    db_session.expire_all()
    session = svc._store.get_session(session.id)
    assert session.current_step_ord == 0  # not advanced


@pytest.mark.asyncio
async def test_auto_advance_disabled_by_default(db_session, monkeypatch) -> None:
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
    voice = _RecordingVoice()

    # auto_advance is False
    routine_id = _seed_routine_with_auto_advance(db_session, auto_advance=False)
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=voice,
        escalator=_RecordingEscalator(),
        settings=_settings(),
        time_fn=clock,
        gate_runner=gate_runner,
    )
    session = await svc.start(routine_id, "resident-1")

    # Run 3 watch checks -> should NOT advance
    for _ in range(3):
        await svc.tick(clock.now)
        clock.advance(25)

    db_session.expire_all()
    session = svc._store.get_session(session.id)
    assert session.current_step_ord == 0


@pytest.mark.asyncio
async def test_safety_critical_step_never_auto_advances(db_session, monkeypatch) -> None:
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
    voice = _RecordingVoice()

    # step is_safety_critical = True
    routine_id = _seed_routine_with_auto_advance(
        db_session, auto_advance=True, is_safety_critical=True
    )
    svc = GuidedTaskService(
        db_factory=lambda: db_session,
        voice=voice,
        escalator=_RecordingEscalator(),
        settings=_settings(),
        time_fn=clock,
        gate_runner=gate_runner,
    )
    session = await svc.start(routine_id, "resident-1")

    # Run 3 watch checks -> should NOT advance
    for _ in range(3):
        await svc.tick(clock.now)
        clock.advance(25)

    db_session.expire_all()
    session = svc._store.get_session(session.id)
    assert session.current_step_ord == 0
