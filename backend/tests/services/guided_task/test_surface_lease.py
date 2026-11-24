"""A guided session wakes and leases the surface in her room, and hands it back.

Runs the real ``ConnectionManager`` and ``AgentSessionVoice`` so the routing under
test is the production routing: the kitchen tablet hears and shows the routine,
the bedroom tablet never does, and the session's end closes the kitchen
microphone lease.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from backend.core.config import Settings
from backend.models.guided_task import Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.guided_task.agent_voice import AgentSessionVoice
from backend.services.guided_task.service import GuidedTaskService
from backend.services.knowledge.voice_instructions import VoiceInstructionConfig
from backend.websocket.connection_manager import ConnectionManager, PromptItem

_SETTINGS = Settings.from_dict(
    {
        "guided_task": {
            "step_timeout_s": 300,
            "max_step_attempts": 3,
            "resume_grace_s": 600,
            "escalation_channels": ["telegram"],
        },
        "companion_surface": {
            "volume_min_pct": 65,
            "attention_chime": "gentle",
            "lease_margin_s": 30,
        },
    }
)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@dataclass(eq=False)
class _Socket:
    sent: list[dict[str, Any]] = field(default_factory=list)

    async def accept(self, subprotocol: str | None = None) -> None:
        return None

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    def of_type(self, kind: str) -> list[dict[str, Any]]:
        return [p for p in self.sent if p.get("type") == kind]


@dataclass(eq=False)
class _AudioSession:
    conversation_session_id: int | None = None
    prompts: list[PromptItem] = field(default_factory=list)

    async def release_voice_instruction(self, owner: str) -> bool:
        return False

    def enqueue_prompt(self, item: PromptItem) -> None:
        self.prompts.append(item)


def _seed(db_session, *, step_timeout_s: int | None = None) -> int:
    db_session.add(HouseholdMember(id="resident-1", name="Ruth"))
    db_session.flush()
    routine = Routine(name="Make tea", person_id="resident-1", is_enabled=True)
    routine.steps.append(
        RoutineStep(
            ord=0, prompt_template="Fill the kettle.", step_timeout_s_override=step_timeout_s
        )
    )
    routine.steps.append(RoutineStep(ord=1, prompt_template="Switch it on."))
    db_session.add(routine)
    db_session.commit()
    return routine.id


async def _house() -> tuple[ConnectionManager, _Socket, _Socket, _AudioSession]:
    manager = ConnectionManager()
    kitchen, bedroom = _Socket(), _Socket()
    await manager.connect(kitchen, surface_id="kitchen-tablet")  # type: ignore[arg-type]
    await manager.connect(bedroom, surface_id="bedroom-tablet")  # type: ignore[arg-type]
    kitchen_session = _AudioSession()
    manager.register_audio_handler(kitchen_session, surface_id="kitchen-tablet")
    manager.register_audio_handler(_AudioSession(), surface_id="bedroom-tablet")
    return manager, kitchen, bedroom, kitchen_session


def _service(db_factory, manager: ConnectionManager, clock: _Clock) -> GuidedTaskService:
    return GuidedTaskService(
        db_factory=db_factory,
        settings=_SETTINGS,
        time_fn=clock,
        ws_manager=manager,
        voice=AgentSessionVoice(manager, VoiceInstructionConfig(), settings=_SETTINGS),
    )


@pytest.mark.asyncio
async def test_spoken_step_wakes_only_her_surface_with_a_step_scaled_lease(
    db_session, db_factory
) -> None:
    routine_id = _seed(db_session, step_timeout_s=600)
    manager, kitchen, bedroom, kitchen_session = await _house()
    service = _service(db_factory, manager, _Clock())

    session = await service.start(routine_id, "resident-1", surface_id="kitchen-tablet")

    # Once before the step is spoken, once renewed with the session's announcement.
    wake = kitchen.of_type("surface_hardware_command")[0]
    assert all(c["enable_microphone"] for c in kitchen.of_type("surface_hardware_command"))
    assert wake["wake_screen"] is True
    assert wake["enable_microphone"] is True
    assert wake["enable_camera"] is False
    # The lease outlives the step's own timeout, so the microphone is still open
    # when the retry prompt renews it.
    assert wake["lease_seconds"] == 630
    assert wake["volume_min_pct"] == 65
    # The lease belongs to this session, so another delivery's release cannot end it.
    assert {c["lease_owner"] for c in kitchen.of_type("surface_hardware_command")} == {
        f"guided_task_start:{session.id}"
    }
    assert kitchen.of_type("enable_microphone")
    assert kitchen.of_type("guided_session_state")[0]["prompt_text"] == "Fill the kettle."
    assert len(kitchen_session.prompts) == 1
    assert bedroom.sent == []
    assert manager.prompt_queue.empty()


@pytest.mark.asyncio
async def test_each_step_renews_the_lease_and_completion_releases_it(
    db_session, db_factory
) -> None:
    routine_id = _seed(db_session, step_timeout_s=600)
    manager, kitchen, bedroom, _ = await _house()
    service = _service(db_factory, manager, _Clock())
    session = await service.start(routine_id, "resident-1", surface_id="kitchen-tablet")
    kitchen.sent.clear()

    # The agent's tool call advances to step 1 without speaking it again, so the
    # renewal must come from the transition itself, with step 1's own timeout.
    await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})
    [renewal] = kitchen.of_type("surface_hardware_command")
    assert (renewal["enable_microphone"], renewal["lease_seconds"]) == (True, 330)

    await service.handle_completion(session.id, {"confirmed": True, "step_ord": 1})

    release = kitchen.of_type("surface_hardware_command")[-1]
    assert release["enable_microphone"] is False
    assert (release["enable_camera"], release["wake_screen"], release["lease_seconds"]) == (
        False,
        False,
        0,
    )
    assert bedroom.sent == []


@pytest.mark.asyncio
async def test_abandon_releases_the_surface(db_session, db_factory) -> None:
    routine_id = _seed(db_session)
    manager, kitchen, _, _ = await _house()
    clock = _Clock()
    service = _service(db_factory, manager, clock)
    session = await service.start(routine_id, "resident-1", surface_id="kitchen-tablet")
    clock.now += timedelta(seconds=601)

    decision = await service.resume(session.id)

    assert decision.kind == "abandon"

    assert kitchen.of_type("surface_hardware_command")[-1]["enable_microphone"] is False


@pytest.mark.asyncio
async def test_hydration_read_matches_what_the_broadcast_reached(db_session, db_factory) -> None:
    routine_id = _seed(db_session)
    manager, _, _, _ = await _house()
    service = _service(db_factory, manager, _Clock())
    await service.start(routine_id, "resident-1", surface_id="kitchen-tablet")

    assert await service.get_resident_state(surface_id="kitchen-tablet") is not None
    # The bedroom screen was never sent this routine, so a reload there must not show it.
    assert await service.get_resident_state(surface_id="bedroom-tablet") is None

    # Once the kitchen tablet is gone the routine falls back to every screen.
    kitchen_socket = next(
        ws for ws in manager.active_connections if manager.is_surface_connected("kitchen-tablet")
    )
    await manager.disconnect(kitchen_socket)
    assert await service.get_resident_state(surface_id="bedroom-tablet") is not None
