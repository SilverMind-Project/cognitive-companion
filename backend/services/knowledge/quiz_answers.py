"""Quiz answers: recording an answer from either channel and driving both views onward.

Part of :class:`~backend.services.knowledge.delivery_service.KnowledgeDeliveryService`.
The tablet and the realtime voice agent can answer the same question at nearly the
same moment; the session row is locked while the ordinal is checked and the answer
written, and the slow part (open-ended grading, a model call) runs outside the lock.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.knowledge import QuizQuestion, QuizResponse, QuizSession
from backend.services.interactive_session import (
    cancel_session_timeout,
    inject_session_prompt,
    voice_owner_key,
)
from backend.services.knowledge.delivery_context import DeliveryContextMixin
from backend.services.knowledge.quiz_messages import (
    QUIZ_DELIVERY_TYPE,
    TERMINAL_QUIZ_STATUSES,
    AnswerTarget,
    question_descriptor,
    quiz_timeout_job_id,
    spoken_question,
    tablet_answer_summary,
)
from backend.services.knowledge.voice_instructions import QuizInteractionMode

# Logged under the delivery service's logger so existing log queries keep matching.
logger = get_logger("backend.services.knowledge.delivery_service")


class QuizAnswersMixin(DeliveryContextMixin):
    """Answer recording, grading, and next-question fanout for quiz sessions."""

    _content_gen: Any
    _scheduler: Any
    _voice_sessions: set[int]
    complete_quiz_session: Callable[[int], Awaitable[dict[str, Any]]]
    _send_question_ws: Callable[
        [int, QuizQuestion, int, int, QuizInteractionMode | None], Awaitable[None]
    ]

    # -- answers -------------------------------------------------------------

    async def submit_quiz_answer(
        self,
        session_id: int,
        question_ord: int,
        *,
        choice_id: str | None = None,
        open_ended_text: str | None = None,
        channel: str = "voice",
        latency_ms: int | None = None,
    ) -> dict[str, Any]:
        """Record the senior's answer, advance the session, and drive both views.

        Safe against the tablet and the voice agent answering the same question: the
        session row is locked while the ordinal is checked and the answer is written,
        a repeat of an answered question returns the recorded result, and an answer
        for a question that is not current is rejected with the current question.
        Returns ``next_question`` so the voice agent can ask it without another call.
        ``latency_ms`` defaults to the time since the question was presented.
        """
        checked = self._check_answer_target(session_id, question_ord)
        if isinstance(checked, dict):
            return checked
        question = checked.question

        is_correct, chosen_text = await self._grade(question, choice_id, open_ended_text)
        answered_at = datetime.now(UTC)
        if latency_ms is None:
            latency_ms = max(
                0, int((answered_at - checked.started_reference).total_seconds() * 1000)
            )

        recorded = self._record_answer(
            session_id,
            question_ord,
            question,
            choice_id=choice_id,
            chosen_text=chosen_text,
            open_ended_text=open_ended_text,
            is_correct=is_correct,
            channel=channel,
            latency_ms=latency_ms,
            answered_at=answered_at,
        )
        if isinstance(recorded, dict):
            return recorded
        next_question = recorded

        total = checked.total
        completed = next_question is None
        if completed:
            # Cancel the timeout job before awaiting broadcasts so it cannot fire
            # during the window before complete_quiz_session commits.
            cancel_session_timeout(self._scheduler, job_id=quiz_timeout_job_id(session_id))
        result: dict[str, Any] = {
            "session_id": session_id,
            "question_ord": question_ord,
            "is_correct": is_correct,
            "explanation": question.explanation or "",
            "advance": not completed,
            "completed": completed,
            "next_question": (
                question_descriptor(next_question, question_ord + 1, total)
                if next_question is not None
                else None
            ),
        }
        await self._announce_answer(result)

        answered = tablet_answer_summary(
            question_ord,
            chosen_text or open_ended_text or "",
            is_correct,
            question.explanation or "",
        )
        if next_question is not None:
            await self._present_next_question(
                session_id, next_question, question_ord + 1, total, channel, answered
            )
        else:
            await self._relay_quiz_end(session_id, channel, answered)
            await self.complete_quiz_session(session_id)
        return result

    def _check_answer_target(
        self, session_id: int, question_ord: int
    ) -> AnswerTarget | dict[str, Any]:
        """Locked read: is ``question_ord`` the question this session is waiting on?"""
        db: Session = self._db_factory()
        try:
            session = db.execute(
                select(QuizSession).where(QuizSession.id == session_id).with_for_update()
            ).scalar_one_or_none()
            if session is None:
                return {"error": "Session not found"}
            if session.status in TERMINAL_QUIZ_STATUSES:
                return {
                    "session_id": session_id,
                    "question_ord": question_ord,
                    "status": session.status,
                    "advance": False,
                    "completed": True,
                    "next_question": None,
                }
            question_order: list[int] = session.question_order or []
            total = len(question_order)
            if question_ord < 0 or question_ord >= total:
                return {"error": f"question_ord {question_ord} out of range [0, {total})"}

            if question_ord != session.current_question_ord:
                return self._not_current_answer(db, session, question_ord, total)

            question = db.get(QuizQuestion, question_order[question_ord])
            if question is None:
                return {"error": "Question not found"}
            db.expunge(question)
            return AnswerTarget(
                question=question,
                total=total,
                started_reference=session.last_activity_at,
            )
        finally:
            db.rollback()
            db.close()

    def _not_current_answer(
        self, db: Session, session: QuizSession, question_ord: int, total: int
    ) -> dict[str, Any]:
        """A repeat of an answered question returns its recorded result; a skip-ahead is
        rejected. Either way the caller learns which question is current."""
        current_ord = session.current_question_ord
        current: dict[str, Any] | None = None
        if current_ord < total:
            current_q = db.get(QuizQuestion, (session.question_order or [])[current_ord])
            if current_q is not None:
                current = question_descriptor(current_q, current_ord, total)

        prior = db.execute(
            select(QuizResponse).where(
                QuizResponse.session_id == session.id,
                QuizResponse.question_ord == question_ord,
            )
        ).scalar_one_or_none()
        if prior is not None:
            return {
                "session_id": session.id,
                "question_ord": question_ord,
                "is_correct": prior.is_correct,
                "duplicate": True,
                "advance": current is not None,
                "completed": False,
                "next_question": current,
            }
        return {
            "error": "not_current_question",
            "session_id": session.id,
            "question_ord": question_ord,
            "current_question": current,
        }

    async def _grade(
        self,
        question: QuizQuestion,
        choice_id: str | None,
        open_ended_text: str | None,
    ) -> tuple[bool | None, str]:
        """Grade outside any row lock: open-ended grading is a model call."""
        if question.question_type == "multiple_choice" and choice_id:
            for choice in question.choices or []:
                if choice.get("id") == choice_id:
                    return bool(choice.get("is_correct", False)), choice.get("text", "")
            return None, ""
        if (
            question.question_type == "open_ended"
            and open_ended_text
            and self._content_gen is not None
            and question.expected_answer
        ):
            try:
                graded = await self._content_gen.grade_open_ended(
                    question.question_text, question.expected_answer, open_ended_text
                )
            except Exception:
                logger.exception("open_ended_grading_failed", question_id=question.id)
                return None, ""
            return bool(graded), ""
        return None, ""

    def _record_answer(
        self,
        session_id: int,
        question_ord: int,
        question: QuizQuestion,
        *,
        choice_id: str | None,
        chosen_text: str,
        open_ended_text: str | None,
        is_correct: bool | None,
        channel: str,
        latency_ms: int,
        answered_at: datetime,
    ) -> QuizQuestion | dict[str, Any] | None:
        """Write the answer and advance, re-checking the ordinal under the lock.

        Returns the next question (None after the last one), or a result dict when the
        other channel answered this question while it was being graded.
        """
        db: Session = self._db_factory()
        try:
            session = db.execute(
                select(QuizSession).where(QuizSession.id == session_id).with_for_update()
            ).scalar_one_or_none()
            if (
                session is None
                or session.status in TERMINAL_QUIZ_STATUSES
                or session.current_question_ord != question_ord
            ):
                db.rollback()
                return self._lost_race_result(session_id, question_ord)

            db.add(
                QuizResponse(
                    session_id=session_id,
                    question_id=question.id,
                    question_ord=question_ord,
                    question_text=question.question_text,
                    chosen_choice_id=choice_id,
                    chosen_choice_text=chosen_text,
                    open_ended_text=open_ended_text,
                    is_correct=is_correct,
                    channel=channel,
                    latency_ms=latency_ms,
                )
            )
            session.current_question_ord = question_ord + 1
            session.last_activity_at = answered_at
            if session.status == "started":
                session.status = "in_progress"
            order: list[int] = session.question_order or []
            next_question = (
                db.get(QuizQuestion, order[question_ord + 1])
                if question_ord + 1 < len(order)
                else None
            )
            db.commit()
            if next_question is not None:
                db.expunge(next_question)
            return next_question
        except IntegrityError:
            db.rollback()
            return self._lost_race_result(session_id, question_ord)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _lost_race_result(self, session_id: int, question_ord: int) -> dict[str, Any]:
        checked = self._check_answer_target(session_id, question_ord)
        if isinstance(checked, dict):
            return checked
        # Still current after a lost race means the competing write failed; ask again.
        return {"error": "answer_not_recorded", "session_id": session_id}

    async def _announce_answer(self, result: dict[str, Any]) -> None:
        try:
            await self._send_to_resident(
                voice_owner_key(QUIZ_DELIVERY_TYPE, result["session_id"]),
                {
                    "type": "quiz_answer_recorded",
                    "session_id": result["session_id"],
                    "question_ord": result["question_ord"],
                    "is_correct": result["is_correct"],
                    "explanation": result["explanation"],
                    "advance": result["advance"],
                },
            )
        except Exception:
            logger.exception("quiz_answer_recorded_broadcast_failed")

    async def _present_next_question(
        self,
        session_id: int,
        question: QuizQuestion,
        ord_num: int,
        total: int,
        channel: str,
        answered: str,
    ) -> None:
        try:
            await self._send_question_ws(session_id, question, ord_num, total, None)
        except Exception:
            logger.exception("quiz_question_broadcast_failed", session_id=session_id)

        # A voice answer already gets the next question in its tool result. A tap on
        # the tablet does not reach the agent, so tell it, or it keeps asking the old
        # question while the screen shows the new one.
        if channel != "voice" and session_id in self._voice_sessions:
            try:
                await inject_session_prompt(
                    self._ws_manager,
                    prompt=(
                        f"{answered} Respond to that answer, then ask the next one. "
                        f"{spoken_question(session_id, question, ord_num)}"
                    ),
                    delivery_type=QUIZ_DELIVERY_TYPE,
                    session_id=session_id,
                    surface_id=self._resident_surface(
                        voice_owner_key(QUIZ_DELIVERY_TYPE, session_id)
                    ),
                )
            except Exception:
                logger.exception("quiz_voice_sync_failed", session_id=session_id)

    async def _relay_quiz_end(self, session_id: int, channel: str, answered: str) -> None:
        """Tell the voice agent a tablet-finished quiz is over.

        Without it the agent's transcript ends on an unanswered question, and it may ask
        it again. Sent before the persona is released; it carries no instruction.
        """
        if channel == "voice" or session_id not in self._voice_sessions:
            return
        try:
            await inject_session_prompt(
                self._ws_manager,
                prompt=(
                    f"{answered} That was the last question, so the questions are "
                    "finished. Respond to that answer, thank them warmly for chatting, "
                    "and do not ask any more questions."
                ),
                delivery_type=QUIZ_DELIVERY_TYPE,
                session_id=session_id,
                surface_id=self._resident_surface(voice_owner_key(QUIZ_DELIVERY_TYPE, session_id)),
            )
        except Exception:
            logger.exception("quiz_voice_end_relay_failed", session_id=session_id)
