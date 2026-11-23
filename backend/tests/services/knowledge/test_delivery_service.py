"""KnowledgeDeliveryService against the real database.

Covers the quiz session lifecycle (start, answers from either channel, completion,
timeout), voice and tablet lockstep, persona composition and release, and
delivery-time template rendering for info cards.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import selectinload

from backend.core.exceptions import ValidationError
from backend.models.knowledge import InfoCard, InfoCardDelivery, Quiz, QuizResponse, QuizSession
from backend.tests.factories import make_household_member
from backend.tests.factories.knowledge import (
    multiple_choice,
    seed_execution,
    seed_info_card,
    seed_quiz,
)
from backend.tests.factories.knowledge_delivery import (
    BASE_PERSONA,
    FakeGrader,
    make_delivery,
)

pytestmark = pytest.mark.asyncio


def _load_quiz(db_session, quiz_id: int) -> Quiz:
    db_session.expire_all()
    return (
        db_session.query(Quiz)
        .options(selectinload(Quiz.questions))
        .filter(Quiz.id == quiz_id)
        .one()
    )


def _two_question_quiz(db_session) -> Quiz:
    quiz = seed_quiz(
        db_session,
        [
            multiple_choice(
                "Who is Priya?",
                "Your granddaughter",
                "Your neighbour",
                explanation="Priya is your granddaughter who lives in Boston.",
            ),
            multiple_choice("Where is Boston?", "America", "India"),
        ],
        intro_voice_template="Hello {{senior_name}}, shall we chat?",
    )
    return _load_quiz(db_session, quiz.id)


async def _start(db_session, db_factory, *, channels=None, mode="gentle", grader=None):
    execution = seed_execution(db_session)
    db_session.add(make_household_member("resident-1", "Kamala"))
    db_session.commit()
    quiz = _two_question_quiz(db_session)
    delivery, ws, scheduler = make_delivery(db_factory, grader=grader)
    result = await delivery.start_quiz_session(
        quiz,
        execution_id=execution.id,
        channels=channels,
        interaction_mode=mode,
        senior_id="resident-1",
    )
    return delivery, ws, scheduler, result, execution


def _session(db_session, session_id: int) -> QuizSession:
    db_session.expire_all()
    return db_session.get(QuizSession, session_id)


# -- start --------------------------------------------------------------------


async def test_start_asks_question_one_with_choices_on_a_live_mic_and_base_persona(
    db_session, db_factory
):
    _delivery, ws, scheduler, result, _execution = await _start(db_session, db_factory)

    task = ws.backend_tasks[0]
    assert "Hello Kamala, shall we chat?" in task["prompt"]
    assert "question_ord=0" in task["prompt"]
    assert "choice_id a: Your granddaughter" in task["prompt"]
    assert "choice_id b: Your neighbour" in task["prompt"]
    instruction = task["voice_instruction"]
    assert instruction.startswith(BASE_PERSONA)
    assert "Ask one question at a time." in instruction
    assert instruction.endswith("GENTLE: never say wrong.")
    assert task["metadata"]["delivery_type"] == "quiz_start"

    # The microphone is live before the question is spoken.
    assert ws.order.index("enable_microphone") < ws.order.index("backend_task")
    start = ws.of_type("quiz_start")[0]
    assert start["interaction_mode"] == "gentle"
    assert start["voice"] is True
    question = ws.of_type("quiz_question")[0]
    assert question["question_ord"] == 0
    assert question["hint"] == "Priya is your granddaughter who lives in Boston."

    stored = _session(db_session, result.session_id)
    assert stored.senior_id == "resident-1"
    assert stored.status == "in_progress"
    assert len(stored.question_order) == 2
    assert scheduler.apscheduler.get_job(f"quiz_timeout_{result.session_id}") is not None
    assert result.timeout_at is not None


async def test_standard_mode_composes_the_standard_directive(db_session, db_factory):
    _delivery, ws, _scheduler, _result, _ = await _start(db_session, db_factory, mode="standard")

    assert ws.backend_tasks[0]["voice_instruction"].endswith("STANDARD: say whether it was right.")


async def test_tablet_only_quiz_never_wakes_the_voice_agent(db_session, db_factory):
    delivery, ws, _scheduler, result, _ = await _start(db_session, db_factory, channels=["pwa"])

    assert ws.backend_tasks == []
    assert ws.of_type("enable_microphone") == []

    await delivery.submit_quiz_answer(result.session_id, 0, choice_id="a", channel="pwa")

    assert ws.backend_tasks == [], "a tablet tap must not open a realtime session"


async def test_quiz_with_no_questions_raises_before_writing_a_session(db_session, db_factory):
    execution = seed_execution(db_session)
    quiz = _load_quiz(db_session, seed_quiz(db_session, []).id)
    delivery, _ws, _scheduler = make_delivery(db_factory)

    with pytest.raises(ValidationError):
        await delivery.start_quiz_session(quiz, execution_id=execution.id)

    assert db_session.query(QuizSession).count() == 0


# -- answers ------------------------------------------------------------------


async def test_answer_returns_next_question_and_explanation(db_session, db_factory):
    delivery, ws, _scheduler, result, _ = await _start(db_session, db_factory)

    answer = await delivery.submit_quiz_answer(result.session_id, 0, choice_id="b")

    assert answer["is_correct"] is False
    assert answer["explanation"] == "Priya is your granddaughter who lives in Boston."
    assert answer["completed"] is False
    assert answer["next_question"]["question_ord"] == 1
    assert answer["next_question"]["question_text"] == "Where is Boston?"
    recorded = ws.of_type("quiz_answer_recorded")[-1]
    assert recorded["explanation"] == answer["explanation"]
    assert ws.of_type("quiz_question")[-1]["question_ord"] == 1


async def test_repeating_an_answered_question_is_idempotent(db_session, db_factory):
    delivery, _ws, _scheduler, result, _ = await _start(db_session, db_factory)

    first = await delivery.submit_quiz_answer(result.session_id, 0, choice_id="a")
    again = await delivery.submit_quiz_answer(result.session_id, 0, choice_id="b", channel="pwa")

    assert first["is_correct"] is True
    assert again["duplicate"] is True
    assert again["is_correct"] is True
    assert again["next_question"]["question_ord"] == 1
    db_session.expire_all()
    assert db_session.query(QuizResponse).count() == 1


async def test_answer_for_a_question_not_yet_asked_is_rejected(db_session, db_factory):
    delivery, _ws, _scheduler, result, _ = await _start(db_session, db_factory)

    answer = await delivery.submit_quiz_answer(result.session_id, 1, choice_id="a")

    assert answer["error"] == "not_current_question"
    assert answer["current_question"]["question_ord"] == 0
    assert db_session.query(QuizResponse).count() == 0


async def test_tablet_answer_on_a_voice_quiz_tells_the_agent_the_next_question(
    db_session, db_factory
):
    delivery, ws, _scheduler, result, _ = await _start(db_session, db_factory)
    ws.backend_tasks.clear()

    await delivery.submit_quiz_answer(result.session_id, 0, choice_id="a", channel="pwa")

    assert len(ws.backend_tasks) == 1
    sync = ws.backend_tasks[0]
    assert "answered question 0 on the tablet" in sync["prompt"]
    assert "question_ord=1" in sync["prompt"]
    assert "Where is Boston?" in sync["prompt"]
    # The persona set at quiz start stays; the relay does not reopen the session.
    assert sync["voice_instruction"] is None


async def test_voice_answer_is_not_relayed_back_to_the_agent(db_session, db_factory):
    delivery, ws, _scheduler, result, _ = await _start(db_session, db_factory)
    ws.backend_tasks.clear()

    await delivery.submit_quiz_answer(result.session_id, 0, choice_id="a", channel="voice")

    assert ws.backend_tasks == []


async def test_latency_defaults_to_time_since_the_question_was_presented(db_session, db_factory):
    delivery, _ws, _scheduler, result, _ = await _start(db_session, db_factory)
    db_session.query(QuizSession).filter(QuizSession.id == result.session_id).update(
        {"last_activity_at": datetime.now(UTC) - timedelta(seconds=7)}
    )
    db_session.commit()

    await delivery.submit_quiz_answer(result.session_id, 0, choice_id="a")

    response = db_session.query(QuizResponse).one()
    assert 7000 <= response.latency_ms < 60000


async def test_caller_supplied_latency_is_kept(db_session, db_factory):
    delivery, _ws, _scheduler, result, _ = await _start(db_session, db_factory)

    await delivery.submit_quiz_answer(result.session_id, 0, choice_id="a", latency_ms=1234)

    assert db_session.query(QuizResponse).one().latency_ms == 1234


async def test_open_ended_answer_is_graded(db_session, db_factory):
    execution = seed_execution(db_session)
    quiz = seed_quiz(
        db_session,
        [
            {
                "question_type": "open_ended",
                "question_text": "What did you have for breakfast?",
                "expected_answer": "Idli",
            }
        ],
    )
    grader = FakeGrader(verdict=True)
    delivery, _ws, _scheduler = make_delivery(db_factory, grader=grader)
    started = await delivery.start_quiz_session(
        _load_quiz(db_session, quiz.id), execution_id=execution.id
    )

    answer = await delivery.submit_quiz_answer(
        started.session_id, 0, open_ended_text="idli and chutney"
    )

    assert grader.calls == 1
    assert answer["is_correct"] is True
    assert answer["completed"] is True


async def test_tablet_and_voice_answering_at_once_record_one_answer(db_session, db_factory):
    """Both channels pass the first check, then race to write: exactly one wins and
    the other gets the recorded result instead of a constraint error."""
    execution = seed_execution(db_session)
    quiz = seed_quiz(
        db_session,
        [
            {"question_type": "open_ended", "question_text": "Q1?", "expected_answer": "x"},
            {"question_type": "open_ended", "question_text": "Q2?", "expected_answer": "y"},
        ],
    )
    delivery, ws, _scheduler = make_delivery(db_factory, grader=FakeGrader())
    started = await delivery.start_quiz_session(
        _load_quiz(db_session, quiz.id), execution_id=execution.id, channels=["pwa"]
    )

    voice, tablet = await asyncio.gather(
        delivery.submit_quiz_answer(started.session_id, 0, open_ended_text="x"),
        delivery.submit_quiz_answer(started.session_id, 0, open_ended_text="x", channel="pwa"),
    )

    assert db_session.query(QuizResponse).count() == 1
    assert sorted([bool(voice.get("duplicate")), bool(tablet.get("duplicate"))]) == [
        False,
        True,
    ]
    assert len(ws.of_type("quiz_answer_recorded")) == 1
    assert _session(db_session, started.session_id).current_question_ord == 1


async def test_tablet_finishing_a_voice_quiz_tells_the_agent_it_is_over(db_session, db_factory):
    delivery, ws, _scheduler, result, _ = await _start(db_session, db_factory)
    session_id = result.session_id
    await delivery.submit_quiz_answer(session_id, 0, choice_id="a", channel="voice")
    ws.backend_tasks.clear()

    await delivery.submit_quiz_answer(session_id, 1, choice_id="a", channel="pwa")

    assert len(ws.backend_tasks) == 1
    closing = ws.backend_tasks[0]
    assert "questions are finished" in closing["prompt"]
    assert "question_ord=" not in closing["prompt"]
    assert closing["voice_instruction"] is None
    # The notice is queued before the persona is released.
    assert ws.order.index("backend_task") < ws.order.index("quiz_complete")
    assert ws.releases == [f"quiz_start:{session_id}"]


async def test_voice_finishing_a_quiz_sends_no_extra_notice(db_session, db_factory):
    delivery, ws, _scheduler, result, _ = await _start(db_session, db_factory)
    await delivery.submit_quiz_answer(result.session_id, 0, choice_id="a")
    ws.backend_tasks.clear()

    await delivery.submit_quiz_answer(result.session_id, 1, choice_id="a")

    assert ws.backend_tasks == []


# -- terminal transitions -----------------------------------------------------


async def test_last_answer_completes_cancels_timeout_releases_persona_and_resumes(
    db_session, db_factory
):
    delivery, ws, scheduler, result, execution = await _start(db_session, db_factory)
    session_id = result.session_id

    await delivery.submit_quiz_answer(session_id, 0, choice_id="a")
    last = await delivery.submit_quiz_answer(session_id, 1, choice_id="a")

    assert last["completed"] is True
    assert last["next_question"] is None
    assert _session(db_session, session_id).status == "completed"
    assert scheduler.apscheduler.get_job(f"quiz_timeout_{session_id}") is None
    assert ws.releases == [f"quiz_start:{session_id}"]
    assert scheduler.resumes == [execution.id]
    complete = ws.of_type("quiz_complete")
    assert len(complete) == 1
    assert complete[0]["num_correct"] == 2


async def test_timeout_after_completion_never_overwrites_completed(db_session, db_factory):
    delivery, ws, scheduler, result, _ = await _start(db_session, db_factory)
    session_id = result.session_id
    await delivery.complete_quiz_session(session_id)

    await delivery.handle_session_timeout(session_id)

    assert _session(db_session, session_id).status == "completed"
    assert ws.of_type("quiz_timeout") == []
    assert len(scheduler.resumes) == 1


async def test_timeout_of_an_open_session_closes_tablet_releases_persona_and_resumes(
    db_session, db_factory
):
    delivery, ws, scheduler, result, execution = await _start(db_session, db_factory)
    session_id = result.session_id

    await delivery.handle_session_timeout(session_id)

    stored = _session(db_session, session_id)
    assert stored.status == "timed_out"
    assert stored.completed_at is not None
    assert ws.of_type("quiz_timeout") == [{"type": "quiz_timeout", "session_id": session_id}]
    assert ws.releases == [f"quiz_start:{session_id}"]
    assert scheduler.resumes == [execution.id]


async def test_answer_after_timeout_is_refused_as_completed(db_session, db_factory):
    delivery, _ws, _scheduler, result, _ = await _start(db_session, db_factory)
    await delivery.handle_session_timeout(result.session_id)

    answer = await delivery.submit_quiz_answer(result.session_id, 0, choice_id="a")

    assert answer["completed"] is True
    assert answer["status"] == "timed_out"
    assert db_session.query(QuizResponse).count() == 0


async def test_completing_twice_broadcasts_and_resumes_once(db_session, db_factory):
    delivery, ws, scheduler, result, _ = await _start(db_session, db_factory)

    await delivery.complete_quiz_session(result.session_id)
    again = await delivery.complete_quiz_session(result.session_id)

    assert again["status"] == "completed"
    assert len(ws.of_type("quiz_complete")) == 1
    assert len(scheduler.resumes) == 1


async def test_current_question_reports_done_for_a_finished_session(db_session, db_factory):
    delivery, _ws, _scheduler, result, _ = await _start(db_session, db_factory)
    assert delivery.get_current_question(result.session_id)["question_ord"] == 0

    await delivery.complete_quiz_session(result.session_id)

    assert delivery.get_current_question(result.session_id) == {
        "done": True,
        "reason": "completed",
    }


# -- info cards -----------------------------------------------------------------


def _load_card(db_session, card_id: int) -> InfoCard:
    db_session.expire_all()
    return (
        db_session.query(InfoCard)
        .options(selectinload(InfoCard.image_slots))
        .filter(InfoCard.id == card_id)
        .one()
    )


async def test_info_card_renders_templates_everywhere_and_keeps_the_persona(db_session, db_factory):
    execution = seed_execution(db_session)
    db_session.add(make_household_member("resident-1", "Kamala"))
    db_session.commit()
    card = _load_card(
        db_session,
        seed_info_card(
            db_session,
            title="Good morning {{senior_name}}",
            body_text="You are in the {{trigger.room_name}}.",
            voice_instruction="Speak slowly to {{senior_name}}.",
        ).id,
    )
    delivery, ws, _scheduler = make_delivery(db_factory)

    await delivery.deliver_info_card(
        card,
        channels=["pwa", "voice"],
        execution_id=execution.id,
        speak=True,
        senior_id="resident-1",
        template_data={},
        trigger_vars={"room_name": "kitchen", "sensor_id": "cam1"},
    )

    shown = ws.of_type("info_card")[0]
    assert shown["title"] == "Good morning Kamala"
    assert shown["body"] == "You are in the kitchen."
    spoken = ws.backend_tasks[0]
    assert "Good morning Kamala" in spoken["prompt"]
    assert spoken["voice_instruction"] == f"{BASE_PERSONA}\n\nSpeak slowly to Kamala."


async def test_unknown_resident_never_reaches_the_senior_as_a_raw_placeholder(
    db_session, db_factory
):
    execution = seed_execution(db_session)
    card = _load_card(db_session, seed_info_card(db_session, title="Hello {{senior_name}}").id)
    delivery, ws, _scheduler = make_delivery(db_factory)

    await delivery.deliver_info_card(card, channels=["pwa"], execution_id=execution.id)

    assert ws.of_type("info_card")[0]["title"] == "Hello "


async def test_dismissing_a_card_releases_only_its_own_persona(db_session, db_factory):
    execution = seed_execution(db_session)
    card = _load_card(db_session, seed_info_card(db_session).id)
    delivery, ws, _scheduler = make_delivery(db_factory)
    result = await delivery.deliver_info_card(
        card, channels=["pwa", "voice"], execution_id=execution.id, speak=True
    )

    await delivery.handle_info_card_event(result.delivery_id, "viewed")
    assert ws.releases == []
    await delivery.handle_info_card_event(result.delivery_id, "dismissed")

    assert ws.releases == [f"info_card:{result.delivery_id}"]
    stored = db_session.get(InfoCardDelivery, result.delivery_id)
    db_session.refresh(stored)
    assert stored.dismissed_at is not None


async def test_step_without_override_adds_nothing_to_the_persona(db_session, db_factory):
    delivery, _ws, _scheduler = make_delivery(db_factory)

    assert delivery.compose_voice_instruction("interactive_prompt", step_override=None) is None
    assert delivery.compose_voice_instruction(
        "interactive_prompt",
        step_override="Ask about {{trigger.room_name}}.",
        trigger_vars={"room_name": "garden"},
    ) == (f"{BASE_PERSONA}\n\nAsk about garden.")
