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


def tablet_answer_summary(
    question_ord: int, answer_text: str, is_correct: bool | None, explanation: str
) -> str:
    """What the voice agent needs to respond to an answer it did not hear.

    The agent's quiz instructions (gentle or standard) decide the tone; this only gives
    it the facts. Without the explanation the agent cannot offer the reminder that
    errorless learning depends on.
    """
    parts = [f"The senior answered question {question_ord} on the tablet"]
    parts[0] += f': "{answer_text}".' if answer_text else "."
    if is_correct is True:
        parts.append("That matches the expected answer.")
    elif is_correct is False:
        parts.append("That differs from the expected answer.")
        if explanation:
            parts.append(f"Explanation to share as your instructions say: {explanation}")
    return " ".join(parts)
