"""Live session telemetry, the resident-safe tablet state, takeover voice continuity,
and the guided voice persona lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.core.config import Settings
from backend.models.guided_task import GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.guided_task.service import GuidedTaskService

_RESIDENT_KEYS = {
    "type",
    "session_id",
    "routine_id",
    "routine_name",
    "person_id",
    "status",
    "current_step_ord",
    "total_steps",
    "prompt_text",
    "at",
}


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@dataclass
class _ResidentSocket:
    """The companion tablet socket (``/ws/audio``)."""

    broadcasts: list[dict] = field(default_factory=list)
    released: list[str] = field(default_factory=list)
    has_connections: bool = False

    async def broadcast(self, payload: dict) -> None:
        self.broadcasts.append(payload)

    async def release_voice_instruction(self, owner: str) -> bool:
        self.released.append(owner)
        return True


@dataclass
class _Console:
    """The caregiver console broadcaster (``/ws/pipeline``)."""

    events: list[dict] = field(default_factory=list)

    async def __call__(self, payload: dict) -> None:
        self.events.append(payload)


@dataclass
class _Voice:
    spoken: list[int] = field(default_factory=list)

    async def speak_step(self, *, session, step, rendered_prompt: str, is_retry: bool) -> None:
        self.spoken.append(step.ord)


@dataclass
class _MemoryQuery:
    async def search(self, **kwargs):
        return [
            SimpleNamespace(
                description=(
                    "Guided routine 'Make tea' ended with outcome 'abandoned'. "
                    "Duration 840 seconds."
                )
            )
        ]


def _seed(db_session, *, steps: int = 2, prompt: str = "Step {{ step.ord }}") -> int:
    db_session.add(HouseholdMember(id="resident-1", name="Ruth"))
    db_session.flush()
    routine = Routine(name="Make tea", person_id="resident-1", is_enabled=True)
    for ord_ in range(steps):
        routine.steps.append(RoutineStep(ord=ord_, prompt_template=prompt))
    db_session.add(routine)
    db_session.commit()
    return routine.id


def _service(db_factory, clock, **kwargs) -> GuidedTaskService:
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
        time_fn=clock,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_every_transition_reaches_console_and_tablet_once(db_session, db_factory) -> None:
    routine_id = _seed(db_session)
    clock = _Clock()
    tablet, console = _ResidentSocket(), _Console()
    service = _service(
        db_factory, clock, ws_manager=tablet, admin_ws_broadcaster=console, voice=_Voice()
    )

    session = await service.start(routine_id, "resident-1")
    clock.now += timedelta(seconds=300)
    await service.on_step_timeout(session.id)
    await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})
    await service.handle_completion(session.id, {"confirmed": True, "step_ord": 1})

    assert [e["event_kind"] for e in console.events] == [
        "session_started",
        "timeout",
        "step_completed",
        "step_completed",
    ]
    states = [p for p in tablet.broadcasts if p["type"] == "guided_session_state"]
    assert [(s["status"], s["current_step_ord"]) for s in states] == [
        ("active", 0),
        ("active", 0),
        ("active", 1),
        ("completed", 1),
    ]
    assert states[0]["prompt_text"] == "Step 0"
    assert states[0]["total_steps"] == 2
    assert states[-1]["prompt_text"] == ""
    # The tablet never receives the caregiver's diagnostic console event.
    assert all(set(p) == _RESIDENT_KEYS for p in states)
    assert not [p for p in tablet.broadcasts if p["type"] == "guided_session_update"]


@pytest.mark.asyncio
async def test_resident_prompt_omits_agent_memory_context(db_session, db_factory) -> None:
    routine_id = _seed(db_session, steps=1, prompt="Boil water. {{ memory_context }}")
    tablet = _ResidentSocket()
    service = _service(db_factory, _Clock(), ws_manager=tablet, memory_query=_MemoryQuery())

    session = await service.start(routine_id, "resident-1")

    agent_prompt = (await service.get_active_step(session.id))["prompt_text"]
    assert "Last time this routine" in agent_prompt
    state = next(p for p in tablet.broadcasts if p["type"] == "guided_session_state")
    assert state["prompt_text"].strip() == "Boil water."


@pytest.mark.asyncio
async def test_resident_actions_and_help_are_broadcast(db_session, db_factory) -> None:
    routine_id = _seed(db_session)
    console = _Console()
    service = _service(db_factory, _Clock(), admin_ws_broadcaster=console)
    session = await service.start(routine_id, "resident-1")

    await service.repeat_step(session.id)
    await service.report_blocked(session.id, "cannot find the kettle")
    await service.request_help(session.id, "resident_requested")

    assert [e["event_kind"] for e in console.events[1:]] == [
        "step_repeated",
        "step_blocked",
        "help_requested",
    ]
    assert console.events[-1]["status"] == "escalated"


@pytest.mark.asyncio
async def test_release_speaks_a_step_the_caregiver_advanced_to(db_session, db_factory) -> None:
    routine_id = _seed(db_session, steps=3)
    clock = _Clock()
    voice = _Voice()
    service = _service(db_factory, clock, voice=voice)
    session = await service.start(routine_id, "resident-1")
    await service.request_help(session.id)
    assert voice.spoken == [0]

    clock.now += timedelta(seconds=30)
    await service.caregiver_advance(session.id)
    clock.now += timedelta(seconds=30)
    await service.release_takeover(session.id)

    # She hears the step the caregiver moved her to, instead of silence until
    # that step times out.
    assert voice.spoken == [0, 1]
    kinds = [
        e.kind
        for e in db_session.query(GuidedSessionEvent)
        .filter_by(session_id=session.id)
        .order_by(GuidedSessionEvent.id)
    ]
    # Advancing an escalated session is a takeover, and the trail says so.
    assert kinds.index("takeover_started") < kinds.index("takeover_ended")


@pytest.mark.asyncio
async def test_release_without_advance_does_not_repeat_the_step(db_session, db_factory) -> None:
    routine_id = _seed(db_session, steps=2)
    clock = _Clock()
    voice = _Voice()
    service = _service(db_factory, clock, voice=voice)
    session = await service.start(routine_id, "resident-1")

    clock.now += timedelta(seconds=30)
    await service.begin_takeover(session.id)
    clock.now += timedelta(seconds=30)
    await service.release_takeover(session.id)

    assert voice.spoken == [0]


@pytest.mark.asyncio
async def test_terminal_transitions_release_the_guided_voice(db_session, db_factory) -> None:
    routine_id = _seed(db_session, steps=1)
    clock = _Clock()
    tablet = _ResidentSocket()
    service = _service(db_factory, clock, ws_manager=tablet)

    completed = await service.start(routine_id, "resident-1")
    await service.handle_completion(completed.id, {"confirmed": True, "step_ord": 0})
    abandoned = await service.start(routine_id, "resident-1")
    clock.now += timedelta(seconds=700)
    await service.resume(abandoned.id)

    assert tablet.released == [
        f"guided_task_start:{completed.id}",
        f"guided_task_start:{abandoned.id}",
    ]
