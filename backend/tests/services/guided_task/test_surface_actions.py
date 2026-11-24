"""Taps on the resident's guided-task widget, the per-session completion lock,
caregiver-help idempotency, and the tablet's hydration read."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from backend.core.config import Settings
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.guided_task import runtime as runtime_module
from backend.services.guided_task.resident_actions import HELP_REPAGE_AFTER_S
from backend.services.guided_task.service import GuidedTaskService
from backend.tests.factories.companion_socket import CompanionSocketRouting


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@dataclass
class _Voice:
    spoken: list[int] = field(default_factory=list)

    async def speak_step(self, *, session, step, rendered_prompt: str, is_retry: bool) -> None:
        self.spoken.append(step.ord)


@dataclass
class _Escalator:
    calls: list[str] = field(default_factory=list)

    async def escalate(self, *, session, reason: str, emergency: bool) -> None:
        self.calls.append(reason)


@dataclass
class _ResidentSocket(CompanionSocketRouting):
    broadcasts: list[dict] = field(default_factory=list)
    has_connections: bool = False

    async def broadcast(self, payload: dict) -> None:
        self.broadcasts.append(payload)

    async def release_voice_instruction(self, owner: str) -> bool:
        return True


def _seed(db_session, *, steps: int = 3) -> int:
    db_session.add(HouseholdMember(id="resident-1", name="Ruth"))
    db_session.flush()
    routine = Routine(name="Make tea", person_id="resident-1", is_enabled=True)
    for ord_ in range(steps):
        routine.steps.append(RoutineStep(ord=ord_, prompt_template=f"Step {ord_}"))
    db_session.add(routine)
    db_session.commit()
    return routine.id


def _service(db_factory, clock: _Clock | None = None, **kwargs) -> GuidedTaskService:
    return GuidedTaskService(
        db_factory=db_factory,
        settings=Settings.from_dict(
            {
                "guided_task": {
                    "step_timeout_s": 300,
                    "max_step_attempts": 3,
                    "resume_grace_s": 600,
                    "escalation_channels": ["telegram"],
                }
            }
        ),
        time_fn=clock or _Clock(),
        **kwargs,
    )


def _events(db_session, session_id: int, kind: str) -> list[GuidedSessionEvent]:
    db_session.expire_all()
    return (
        db_session.query(GuidedSessionEvent)
        .filter_by(session_id=session_id, kind=kind)
        .order_by(GuidedSessionEvent.id)
        .all()
    )


def _stored(db_session, session_id: int) -> GuidedSession:
    db_session.expire_all()
    return db_session.get(GuidedSession, session_id)


@pytest.mark.asyncio
async def test_done_tap_advances_and_speaks_the_next_step(db_session, db_factory) -> None:
    routine_id = _seed(db_session)
    voice = _Voice()
    service = _service(db_factory, voice=voice)
    session = await service.start(routine_id, "resident-1")

    result = await service.handle_surface_action(session.id, "done", step_ord=0)

    assert result["accepted"] is True
    assert result["advanced"] is True
    assert _stored(db_session, session.id).current_step_ord == 1
    # No agent turn speaks the next step after a tap, so the service does.
    assert voice.spoken == [0, 1]
    [completed] = _events(db_session, session.id, "step_completed")
    assert completed.actor == "resident"


@pytest.mark.asyncio
async def test_done_tap_from_a_stale_screen_completes_nothing(db_session, db_factory) -> None:
    routine_id = _seed(db_session)
    service = _service(db_factory)
    session = await service.start(routine_id, "resident-1")
    await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    # Her screen still showed step 0 when she tapped.
    stale = await service.handle_surface_action(session.id, "done", step_ord=0)
    missing = await service.handle_surface_action(session.id, "done", step_ord=None)

    assert stale == {"accepted": False, "reason": "stale_step_completion"}
    assert missing == {"accepted": False, "reason": "stale_step_completion"}
    assert _stored(db_session, session.id).current_step_ord == 1


@pytest.mark.asyncio
async def test_done_tap_never_advances_during_caregiver_takeover(db_session, db_factory) -> None:
    routine_id = _seed(db_session)
    service = _service(db_factory)
    session = await service.start(routine_id, "resident-1")
    await service.begin_takeover(session.id)

    result = await service.handle_surface_action(session.id, "done", step_ord=0)

    assert result == {"accepted": False, "reason": "caregiver_takeover"}
    stored = _stored(db_session, session.id)
    assert (stored.status, stored.current_step_ord) == ("caregiver_takeover", 0)


@pytest.mark.asyncio
async def test_tap_and_agent_completion_together_advance_one_step(
    db_session, db_factory, monkeypatch
) -> None:
    """She taps "I'm Done" while saying "done", so the agent's tool call lands too.

    The gate suspends (as a vision check does) between the stale-step guard and
    the advance; without the session lock both calls would pass the guard and
    the second would complete step 1, which she has not heard.
    """
    real_evaluate = runtime_module.evaluate_completion

    async def suspending_evaluate(**kwargs):
        await asyncio.sleep(0)
        return await real_evaluate(**kwargs)

    monkeypatch.setattr(runtime_module, "evaluate_completion", suspending_evaluate)
    routine_id = _seed(db_session)
    service = _service(db_factory)
    session = await service.start(routine_id, "resident-1")

    tap, agent = await asyncio.gather(
        service.handle_surface_action(session.id, "done", step_ord=0),
        service.handle_completion(session.id, {"confirmed": True, "step_ord": 0}),
    )

    assert tap["accepted"] is True
    assert agent["advanced"] is False
    assert agent["reason"] == "stale_step_completion"
    assert _stored(db_session, session.id).current_step_ord == 1
    assert len(_events(db_session, session.id, "step_completed")) == 1


@pytest.mark.asyncio
async def test_repeat_tap_speaks_the_current_step_and_records_the_tablet(
    db_session, db_factory
) -> None:
    routine_id = _seed(db_session)
    voice = _Voice()
    service = _service(db_factory, voice=voice)
    session = await service.start(routine_id, "resident-1")

    # "Repeat" is never refused as stale: she asks about the step she is on.
    result = await service.handle_surface_action(session.id, "repeat", step_ord=None)

    assert result == {"accepted": True, "reason": None}
    assert voice.spoken == [0, 0]
    [repeat] = _events(db_session, session.id, "step_repeated")
    assert repeat.detail == {"source": "tablet"}


@pytest.mark.asyncio
async def test_agent_repeat_returns_the_text_without_speaking(db_session, db_factory) -> None:
    routine_id = _seed(db_session)
    voice = _Voice()
    service = _service(db_factory, voice=voice)
    session = await service.start(routine_id, "resident-1")

    result = await service.repeat_step(session.id)

    assert result == {"step_ord": 0, "prompt_text": "Step 0"}
    assert voice.spoken == [0]
    [repeat] = _events(db_session, session.id, "step_repeated")
    assert repeat.detail == {"source": "agent"}


@pytest.mark.asyncio
async def test_help_taps_notify_the_caregiver_once(db_session, db_factory) -> None:
    routine_id = _seed(db_session)
    escalator = _Escalator()
    service = _service(db_factory, escalator=escalator)
    session = await service.start(routine_id, "resident-1")

    first = await service.handle_surface_action(session.id, "help")
    second = await service.handle_surface_action(session.id, "help")

    assert first["accepted"] is True
    assert second["accepted"] is True
    assert escalator.calls == ["resident_tapped_help"]
    assert _stored(db_session, session.id).status == "escalated"
    [requested] = _events(db_session, session.id, "help_requested")
    assert requested.detail == {"reason": "resident_tapped_help", "source": "tablet"}
    # The repeat is on the trail for the console but is not counted as another
    # escalation in the routine metrics.
    assert len(_events(db_session, session.id, "help_repeated")) == 1


@pytest.mark.asyncio
async def test_help_asked_again_after_the_repage_window_pages_again(db_session, db_factory) -> None:
    routine_id = _seed(db_session)
    clock = _Clock()
    escalator = _Escalator()
    service = _service(db_factory, clock, escalator=escalator)
    session = await service.start(routine_id, "resident-1")

    await service.request_help(session.id, "resident_requested")
    clock.now += timedelta(seconds=HELP_REPAGE_AFTER_S - 1)
    absorbed = await service.request_help(session.id, "resident_requested")
    clock.now += timedelta(seconds=1)
    repaged = await service.request_help(session.id, "resident_requested")

    # Still waiting minutes later, she is heard again; a burst of taps is not.
    assert absorbed == {"acknowledged": True, "already_escalated": True}
    assert repaged == {"acknowledged": True}
    assert escalator.calls == ["resident_requested", "resident_requested"]
    assert _stored(db_session, session.id).status == "escalated"


@pytest.mark.asyncio
async def test_help_during_takeover_keeps_the_caregiver_in_control(db_session, db_factory) -> None:
    routine_id = _seed(db_session)
    clock = _Clock()
    escalator = _Escalator()
    service = _service(db_factory, clock, escalator=escalator)
    session = await service.start(routine_id, "resident-1")
    await service.begin_takeover(session.id)
    # A caregiver is with her: no re-page however long it has been.
    clock.now += timedelta(seconds=HELP_REPAGE_AFTER_S * 10)

    result = await service.request_help(session.id, "resident_requested")

    assert result == {"acknowledged": True, "already_escalated": True}
    assert escalator.calls == []
    assert _stored(db_session, session.id).status == "caregiver_takeover"


@pytest.mark.asyncio
async def test_actions_never_reopen_an_ended_session(db_session, db_factory) -> None:
    routine_id = _seed(db_session, steps=1)
    escalator = _Escalator()
    service = _service(db_factory, escalator=escalator)
    session = await service.start(routine_id, "resident-1")
    await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    help_result = await service.request_help(session.id, "resident_requested")
    repeat_result = await service.repeat_step(session.id)
    blocked_result = await service.report_blocked(session.id, "stuck")
    tap = await service.handle_surface_action(session.id, "help")

    ended = {"acknowledged": False, "reason": "session_ended", "status": "completed"}
    assert help_result == repeat_result == blocked_result == ended
    assert tap == {"accepted": False, "reason": "session_not_in_progress"}
    assert escalator.calls == []
    assert _stored(db_session, session.id).status == "completed"


@pytest.mark.asyncio
async def test_resident_state_matches_the_broadcast_and_ignores_idle(
    db_session, db_factory
) -> None:
    routine_id = _seed(db_session)
    clock = _Clock()
    tablet = _ResidentSocket()
    service = _service(db_factory, clock, ws_manager=tablet)

    assert await service.get_resident_state() is None

    session = await service.start(routine_id, "resident-1")
    clock.now += timedelta(seconds=5)
    state = await service.get_resident_state()

    assert state is not None
    broadcast = next(p for p in tablet.broadcasts if p["type"] == "guided_session_state")
    hydrated = state.model_dump(mode="json")
    assert {k: v for k, v in hydrated.items() if k != "at"} == {
        k: v for k, v in broadcast.items() if k != "at"
    }
    assert await service.get_resident_state("someone-else") is None

    await service.caregiver_complete(session.id)
    assert await service.get_resident_state() is None


@pytest.mark.asyncio
async def test_a_summoning_session_has_nothing_on_her_screen(db_session, db_factory) -> None:
    routine_id = _seed(db_session)
    service = _service(db_factory)
    session = await service.start(routine_id, "resident-1")
    db_session.query(GuidedSession).filter_by(id=session.id).update({"status": "summoning"})
    db_session.commit()

    assert await service.get_resident_state() is None
    tap = await service.handle_surface_action(session.id, "done", step_ord=0)
    assert tap == {"accepted": False, "reason": "session_not_in_progress"}
