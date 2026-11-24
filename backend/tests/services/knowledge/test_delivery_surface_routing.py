"""Quiz and info-card delivery to the companion surface in the resident's room.

Uses the real ``ConnectionManager`` with two connected tablets: every message of a
quiz goes to the kitchen tablet named at start, the bedroom tablet sees nothing,
and the kitchen microphone lease is released when the quiz or card ends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy.orm import selectinload

from backend.models.knowledge import Quiz
from backend.services.knowledge.delivery_service import KnowledgeDeliveryService
from backend.tests.factories.knowledge import (
    multiple_choice,
    seed_execution,
    seed_info_card,
    seed_quiz,
)
from backend.tests.factories.knowledge_delivery import (
    BASE_PERSONA,
    VOICE,
    FakeGrader,
    RecordingScheduler,
)
from backend.websocket.connection_manager import ConnectionManager, PromptItem

pytestmark = pytest.mark.asyncio


@dataclass(eq=False)
class _Socket:
    sent: list[dict[str, Any]] = field(default_factory=list)

    async def accept(self, subprotocol: str | None = None) -> None:
        return None

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    def types(self) -> list[str]:
        return [str(p.get("type")) for p in self.sent]

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


async def _house(db_factory) -> tuple[KnowledgeDeliveryService, _Socket, _Socket, _AudioSession]:
    manager = ConnectionManager()
    kitchen, bedroom = _Socket(), _Socket()
    await manager.connect(kitchen, surface_id="kitchen-tablet")  # type: ignore[arg-type]
    await manager.connect(bedroom, surface_id="bedroom-tablet")  # type: ignore[arg-type]
    kitchen_session = _AudioSession()
    manager.register_audio_handler(kitchen_session, surface_id="kitchen-tablet")
    manager.register_audio_handler(_AudioSession(), surface_id="bedroom-tablet")
    delivery = KnowledgeDeliveryService(
        db_factory=db_factory,
        ws_manager=manager,
        voice_instructions=VOICE,
        content_generation=FakeGrader(),
        base_instruction=BASE_PERSONA,
        scheduler=RecordingScheduler(),  # type: ignore[arg-type]
    )
    return delivery, kitchen, bedroom, kitchen_session


def _quiz(db_session) -> Quiz:
    quiz = seed_quiz(db_session, [multiple_choice("Who is Priya?", "Granddaughter", "Neighbour")])
    db_session.expire_all()
    return db_session.query(Quiz).options(selectinload(Quiz.questions)).filter_by(id=quiz.id).one()


async def test_quiz_runs_on_her_surface_only_and_releases_it(db_session, db_factory) -> None:
    execution = seed_execution(db_session)
    quiz = _quiz(db_session)
    delivery, kitchen, bedroom, kitchen_session = await _house(db_factory)

    result = await delivery.start_quiz_session(
        quiz,
        execution_id=execution.id,
        session_timeout_minutes=10,
        surface_id="kitchen-tablet",
    )
    wake = kitchen.of_type("surface_hardware_command")[0]
    assert (wake["enable_microphone"], wake["lease_seconds"]) == (True, 630)
    assert {"quiz_start", "quiz_question", "enable_microphone"} <= set(kitchen.types())
    assert len(kitchen_session.prompts) == 1

    await delivery.submit_quiz_answer(result.session_id, 0, choice_id="a", channel="pwa")

    assert "quiz_complete" in kitchen.types()
    release = kitchen.of_type("surface_hardware_command")[-1]
    assert (release["enable_microphone"], release["lease_seconds"]) == (False, 0)
    assert bedroom.sent == []


async def test_tablet_only_quiz_wakes_the_screen_without_the_microphone(
    db_session, db_factory
) -> None:
    execution = seed_execution(db_session)
    quiz = _quiz(db_session)
    delivery, kitchen, _, _ = await _house(db_factory)

    await delivery.start_quiz_session(
        quiz, execution_id=execution.id, channels=["pwa"], surface_id="kitchen-tablet"
    )

    wake = kitchen.of_type("surface_hardware_command")[0]
    assert (wake["wake_screen"], wake["enable_microphone"]) == (True, False)


async def test_quiz_without_a_surface_reaches_every_screen_and_wakes_none(
    db_session, db_factory
) -> None:
    execution = seed_execution(db_session)
    quiz = _quiz(db_session)
    delivery, kitchen, bedroom, _ = await _house(db_factory)

    await delivery.start_quiz_session(quiz, execution_id=execution.id)

    assert "quiz_start" in kitchen.types()
    assert "quiz_start" in bedroom.types()
    assert not kitchen.of_type("surface_hardware_command")
    assert not bedroom.of_type("surface_hardware_command")


async def test_spoken_card_leases_her_microphone_until_it_is_closed(db_session, db_factory) -> None:
    execution = seed_execution(db_session)
    card = seed_info_card(db_session)
    delivery, kitchen, bedroom, kitchen_session = await _house(db_factory)

    result = await delivery.deliver_info_card(
        card,
        channels=["pwa", "voice"],
        execution_id=execution.id,
        speak=True,
        dismiss_seconds=60,
        surface_id="kitchen-tablet",
    )

    wake = kitchen.of_type("surface_hardware_command")[0]
    assert (wake["enable_microphone"], wake["lease_seconds"]) == (True, 90)
    assert kitchen.of_type("info_card")
    assert len(kitchen_session.prompts) == 1

    assert result.delivery_id is not None
    await delivery.handle_info_card_event(result.delivery_id, "dismissed")

    assert kitchen.of_type("surface_hardware_command")[-1]["enable_microphone"] is False
    assert bedroom.sent == []
