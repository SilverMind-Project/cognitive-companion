"""Persisted seeds for knowledge delivery tests: a parked execution, quizzes, and cards."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.models.event import EventLog
from backend.models.knowledge import InfoCard, Quiz, QuizQuestion, QuizSession
from backend.models.pipeline import WorkflowExecution
from backend.models.rule import Rule


def seed_execution(db: Session, *, status: str = "running") -> WorkflowExecution:
    """A rule and an execution for a delivery to belong to."""
    rule = Rule(name="knowledge-delivery", trigger_types=["manual"], execution_timeout_minutes=0)
    db.add(rule)
    db.flush()
    event = EventLog(
        rule_id=rule.id, rule_name=rule.name, trigger_type="manual", status="processing"
    )
    db.add(event)
    db.flush()
    execution = WorkflowExecution(
        rule_id=rule.id,
        event_log_id=event.id,
        status=status,
        pipeline_data_json={},
        started_at=datetime.now(UTC),
    )
    db.add(execution)
    db.commit()
    return execution


def multiple_choice(text: str, correct: str, wrong: str, explanation: str = "") -> dict[str, Any]:
    return {
        "question_type": "multiple_choice",
        "question_text": text,
        "choices": [
            {"id": "a", "text": correct, "is_correct": True},
            {"id": "b", "text": wrong, "is_correct": False},
        ],
        "explanation": explanation,
    }


def seed_quiz(
    db: Session,
    questions: list[dict[str, Any]],
    *,
    status: str = "approved",
    title: str = "Family",
    intro_voice_template: str = "",
    voice_instruction: str = "",
) -> Quiz:
    quiz = Quiz(
        title=title,
        status=status,
        intro_voice_template=intro_voice_template,
        voice_instruction=voice_instruction,
    )
    db.add(quiz)
    db.flush()
    for ord_num, question in enumerate(questions):
        db.add(
            QuizQuestion(
                quiz_id=quiz.id,
                ord=ord_num,
                question_type=question["question_type"],
                question_text=question["question_text"],
                choices=question.get("choices", []),
                expected_answer=question.get("expected_answer", ""),
                explanation=question.get("explanation", ""),
            )
        )
    db.commit()
    return quiz


def seed_completed_session(db: Session, quiz: Quiz, *, completed_at: datetime) -> QuizSession:
    session = QuizSession(quiz_id=quiz.id, status="completed", completed_at=completed_at)
    db.add(session)
    db.commit()
    return session


def seed_info_card(
    db: Session,
    *,
    title: str = "Lunch",
    body_text: str = "Lunch is at noon.",
    voice_instruction: str = "",
    status: str = "approved",
) -> InfoCard:
    card = InfoCard(
        title=title, body_text=body_text, voice_instruction=voice_instruction, status=status
    )
    db.add(card)
    db.commit()
    return card
