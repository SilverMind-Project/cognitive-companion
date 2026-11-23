"""Quiz delivery: session start, answer recording, completion, and question fanout.

Part of :class:`~backend.services.knowledge.delivery_service.KnowledgeDeliveryService`,
split out by responsibility; it shares that service's injected session factory,
WebSocket manager, MinIO client, voice instructions, grader, and pipeline executor.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.models.knowledge import Quiz, QuizQuestion, QuizResponse, QuizSession
from backend.services.interactive_session import (
    WorkflowResumeScheduler,
    inject_session_prompt,
    resume_owning_pipeline,
)
from backend.services.knowledge.delivery_result import DeliveryResult
from backend.services.knowledge.voice_instructions import VoiceInstructionConfig
from backend.websocket.connection_manager import ConnectionManager

# Logged under the delivery service's logger so existing log queries keep matching.
logger = get_logger("backend.services.knowledge.delivery_service")


class QuizDeliveryMixin:
    """Quiz session lifecycle over the PWA WebSocket and Gemini Live voice."""

    _db_factory: Callable[[], Session]
    _ws_manager: ConnectionManager
    _minio: MinioClient | None
    _voice: VoiceInstructionConfig | None
    _content_gen: Any
    _scheduler: WorkflowResumeScheduler | None

    # -- quiz session delivery ----------------------------------------------

    async def start_quiz_session(
        self,
        quiz: Quiz,
        *,
        execution_id: int,
        rule_id: int | None = None,
        voice_instruction: str | None = None,
        max_questions: int = 5,
        randomize_order: bool = False,
        session_timeout_minutes: int = 10,
    ) -> DeliveryResult:
        """Create quiz_sessions row, broadcast quiz_start ws, speak intro via Gemini."""
        db: Session = self._db_factory()
        try:
            session = QuizSession(
                quiz_id=quiz.id,
                rule_id=rule_id,
                execution_id=execution_id,
                status="started",
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            session_id = session.id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        # Resolve voice instruction
        if self._voice:
            voice_inst = self._voice.compose(
                step_type="quiz",
                base_instruction="",
                step_override=voice_instruction or None,
                resource_override=quiz.voice_instruction or None,
            )
        else:
            voice_inst = voice_instruction or quiz.voice_instruction or ""

        # Get questions, build persisted order
        questions = sorted(quiz.questions or [], key=lambda q: q.ord)
        if randomize_order:
            import random

            random.shuffle(questions)
        questions = questions[:max_questions]
        question_ids = [q.id for q in questions]
        total = len(questions)

        # Persist question_order on the session
        db2: Session = self._db_factory()
        try:
            db2.execute(
                update(QuizSession)
                .where(QuizSession.id == session_id)
                .values(question_order=question_ids)
            )
            db2.commit()
        except Exception:
            db2.rollback()
            logger.exception("question_order_persist_failed", session_id=session_id)
        finally:
            db2.close()

        # PWA popup
        try:
            await self._ws_manager.broadcast(
                {
                    "type": "quiz_start",
                    "session_id": session_id,
                    "quiz_id": quiz.id,
                    "title": quiz.title,
                    "intro_voice_text": quiz.intro_voice_template or "",
                    "total_questions": total,
                }
            )
        except Exception:
            logger.exception("quiz_start_ws_broadcast_failed")

        # Send first question via ws
        if questions:
            q = questions[0]
            await self._send_question_ws(session_id, q, 0, total)

        # Voice delivery
        if voice_inst or quiz.intro_voice_template:
            try:
                intro = quiz.intro_voice_template or f"Let's start the quiz: {quiz.title}."
                voice_prompt = (
                    f"{intro}\n\nThere are {total} questions. "
                    f"Here is the first question.\n\n{q.question_text}"
                )
                await inject_session_prompt(
                    self._ws_manager,
                    prompt=voice_prompt,
                    delivery_type="quiz_start",
                    session_id=session_id,
                    execution_id=execution_id,
                    voice_instruction=voice_inst or None,
                    extra_metadata={
                        "quiz_id": quiz.id,
                    },
                )
                # Transition session to in_progress
                self._update_session_status(session_id, "in_progress")
            except Exception:
                logger.exception("quiz_voice_delivery_failed")

        logger.info(
            "quiz_session_started",
            session_id=session_id,
            quiz_id=quiz.id,
            question_count=total,
        )
        return DeliveryResult(session_id=session_id)

    # -- quiz answers -------------------------------------------------------

    def get_current_question(self, session_id: int) -> dict[str, Any]:
        """Return the question the senior should answer next.

        Returns ord, text, type, choices, or {"done": True} if past the end.
        """
        db: Session = self._db_factory()
        try:
            session = db.execute(
                select(QuizSession).where(QuizSession.id == session_id)
            ).scalar_one_or_none()
            if session is None:
                return {"error": "Session not found"}

            question_order: list[int] = session.question_order or []
            total = len(question_order)
            if total == 0:
                return {"done": True, "reason": "no questions"}

            idx = session.current_question_ord
            if idx >= total:
                return {"done": True, "reason": "past last question"}

            question = db.execute(
                select(QuizQuestion).where(QuizQuestion.id == question_order[idx])
            ).scalar_one_or_none()
            if question is None:
                return {"done": True, "reason": "question not found"}

            return {
                "session_id": session_id,
                "question_ord": idx,
                "question_text": question.question_text,
                "question_type": question.question_type,
                "choices": question.choices or [],
                "total": total,
            }
        finally:
            db.close()

    async def submit_quiz_answer(
        self,
        session_id: int,
        question_ord: int,
        *,
        choice_id: str | None = None,
        open_ended_text: str | None = None,
        channel: str = "pwa_voice",
        latency_ms: int | None = None,
    ) -> dict[str, Any]:
        """Record the senior's answer and advance the session."""
        db: Session = self._db_factory()
        try:
            session = db.execute(
                select(QuizSession).where(QuizSession.id == session_id)
            ).scalar_one_or_none()
            if session is None:
                return {"error": "Session not found"}

            question_order: list[int] = session.question_order or []
            total = len(question_order)
            if total == 0:
                return {"error": "No questions in session"}

            if question_ord < 0 or question_ord >= total:
                return {"error": f"question_ord {question_ord} out of range [0, {total})"}

            question_id = question_order[question_ord]
            question = db.execute(
                select(QuizQuestion).where(QuizQuestion.id == question_id)
            ).scalar_one_or_none()

            if question is None:
                return {"error": "Question not found"}

            # Check is_correct for multiple choice, or grade open_ended via LLM
            is_correct: bool | None = None
            chosen_text = ""
            if question.question_type == "multiple_choice" and choice_id:
                for c in question.choices or []:
                    if c.get("id") == choice_id:
                        chosen_text = c.get("text", "")
                        is_correct = c.get("is_correct", False)
                        break
            elif (
                question.question_type == "open_ended"
                and open_ended_text
                and self._content_gen
                and question.expected_answer
            ):
                try:
                    is_correct = await self._content_gen.grade_open_ended(
                        question.question_text,
                        question.expected_answer,
                        open_ended_text,
                    )
                except Exception:
                    logger.exception("open_ended_grading_failed")
                    is_correct = None

            # Record response (idempotent — only advance on first insert)
            existing = db.execute(
                select(QuizResponse).where(
                    QuizResponse.session_id == session_id,
                    QuizResponse.question_id == question.id,
                )
            ).scalar_one_or_none()

            is_new_response = existing is None
            if is_new_response:
                resp = QuizResponse(
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
                db.add(resp)
                db.commit()

                # Advance session (idempotent: only on new response)
                session.current_question_ord = question_ord + 1
                session.last_activity_at = datetime.now(UTC)
                db.commit()

            # Check if quiz is complete using persisted question_order
            advance = (question_ord + 1) < total

            # Broadcast shared result for both PWA and voice paths
            try:
                await self._ws_manager.broadcast(
                    {
                        "type": "quiz_answer_recorded",
                        "session_id": session_id,
                        "question_ord": question_ord,
                        "is_correct": is_correct,
                        "advance": advance,
                    }
                )
            except Exception:
                logger.exception("quiz_answer_recorded_broadcast_failed")

            # Drive the next question or complete
            if is_new_response:
                if advance:
                    await self._send_question_by_index(session, question_ord + 1)
                else:
                    await self.complete_quiz_session(session_id)

            return {
                "session_id": session_id,
                "question_ord": question_ord,
                "is_correct": is_correct,
                "advance": advance,
            }
        except Exception:
            db.rollback()
            logger.exception("submit_quiz_answer_error")
            return {"error": "Failed to record answer"}
        finally:
            db.close()

    async def complete_quiz_session(self, session_id: int) -> dict[str, Any]:
        """Finalize a quiz session."""
        db: Session = self._db_factory()
        try:
            session = db.execute(
                select(QuizSession).where(QuizSession.id == session_id)
            ).scalar_one_or_none()
            if session is None:
                return {"error": "Session not found"}

            session.status = "completed"
            session.completed_at = datetime.now(UTC)

            # Count results
            responses = (
                db.execute(select(QuizResponse).where(QuizResponse.session_id == session_id))
                .scalars()
                .all()
            )
            num_answered = len(responses)
            num_correct = sum(1 for r in responses if r.is_correct)

            db.commit()
            execution_id = session.execution_id

            # Broadcast completion
            await self._ws_manager.broadcast(
                {
                    "type": "quiz_complete",
                    "session_id": session_id,
                    "num_correct": num_correct,
                    "num_answered": num_answered,
                }
            )

            # Resume the owning pipeline execution so it doesn't wait for timeout
            resume_owning_pipeline(self._scheduler, execution_id)

            logger.info(
                "quiz_session_completed",
                session_id=session_id,
                num_correct=num_correct,
                num_answered=num_answered,
            )
            return {
                "session_id": session_id,
                "status": "completed",
                "num_correct": num_correct,
                "num_answered": num_answered,
            }
        except Exception:
            db.rollback()
            logger.exception("complete_quiz_session_error")
            return {"error": "Failed to complete session"}
        finally:
            db.close()

    # -- helpers ------------------------------------------------------------

    async def _send_question_by_index(self, session: QuizSession, index: int) -> None:
        """Resolve question_order[index], load the QuizQuestion, send via ws."""
        question_order: list[int] = session.question_order or []
        if index < 0 or index >= len(question_order):
            logger.error("question_index_out_of_range", index=index, total=len(question_order))
            return
        question_id = question_order[index]
        db: Session = self._db_factory()
        try:
            question = db.execute(
                select(QuizQuestion).where(QuizQuestion.id == question_id)
            ).scalar_one_or_none()
            if question is None:
                logger.error("question_not_found", question_id=question_id)
                return
            await self._send_question_ws(session.id, question, index, len(question_order))
        finally:
            db.close()

    async def _send_question_ws(
        self, session_id: int, question: QuizQuestion, ord_num: int, total: int
    ) -> None:
        """Send a quiz_question ws message."""
        image_data = None
        if question.image_slot and isinstance(question.image_slot, dict):
            pwa = question.image_slot.get("variants", {}).get("pwa", {})
            object_name = pwa.get("object_name", "")
            url = ""
            if object_name and self._minio:
                try:
                    url = self._minio.generate_presigned_url(object_name)
                except Exception:
                    logger.exception("quiz_presigned_url_failed", object_name=object_name)
            if pwa:
                image_data = {
                    "url": url,
                    "width": pwa.get("width", 0),
                    "height": pwa.get("height", 0),
                    "alt_text": question.image_slot.get("alt_text", ""),
                }

        await self._ws_manager.broadcast(
            {
                "type": "quiz_question",
                "session_id": session_id,
                "question_ord": ord_num,
                "question_type": question.question_type,
                "question_text": question.question_text,
                "choices": [
                    {"id": c.get("id", ""), "text": c.get("text", "")}
                    for c in (question.choices or [])
                ],
                "image": image_data,
                "server_timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def _update_session_status(self, session_id: int, status: str) -> None:
        db: Session = self._db_factory()
        try:
            session = db.execute(
                select(QuizSession).where(QuizSession.id == session_id)
            ).scalar_one_or_none()
            if session and session.status != status:
                session.status = status
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        finally:
            db.close()
