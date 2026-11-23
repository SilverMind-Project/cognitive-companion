"""Quiz wire vocabulary shared by the delivery mixins: statuses, job ids, and payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.models.knowledge import QuizQuestion

QUIZ_DELIVERY_TYPE = "quiz_start"
TERMINAL_QUIZ_STATUSES = frozenset({"completed", "abandoned", "timed_out"})


def quiz_timeout_job_id(session_id: int) -> str:
    return f"quiz_timeout_{session_id}"


@dataclass(frozen=True, slots=True)
class AnswerTarget:
    """What the locked pre-check learned about the answer being submitted."""

    question: QuizQuestion
    total: int
    started_reference: datetime


def question_descriptor(question: QuizQuestion, ord_num: int, total: int) -> dict[str, Any]:
    """The question as both views need it: what to show, what to read aloud."""
    return {
        "question_ord": ord_num,
        "question_type": question.question_type,
        "question_text": question.question_text,
        "choices": [
            {"id": c.get("id", ""), "text": c.get("text", "")} for c in (question.choices or [])
        ],
        "total": total,
    }


def spoken_choices(question: QuizQuestion) -> str:
    if question.question_type != "multiple_choice" or not question.choices:
        return ""
    options = "; ".join(
        f"choice_id {c.get('id', '')}: {c.get('text', '')}" for c in question.choices
    )
    return f" The choices are: {options}."


def spoken_question(session_id: int, question: QuizQuestion, ord_num: int) -> str:
    return (
        f"Question (session_id={session_id}, question_ord={ord_num}): "
        f"{question.question_text}{spoken_choices(question)}"
    )
