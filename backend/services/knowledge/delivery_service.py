"""Pipeline-side delivery: ws fanout, eink render, Gemini Live voice, quiz lifecycle.

Phase 3: full implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.integrations.eink_renderer import EInkRenderer
from backend.integrations.minio_client import MinioClient
from backend.models.knowledge import (
    InfoCard,
    InfoCardDelivery,
    Quiz,
    QuizQuestion,
    QuizResponse,
    QuizSession,
)
from backend.services.knowledge.voice_instructions import VoiceInstructionConfig
from backend.websocket.connection_manager import ConnectionManager

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    delivery_id: int | None = None
    session_id: int | None = None


class KnowledgeDeliveryService:
    """Delivers info cards and quizzes via ws popup, eink, and Gemini Live voice."""

    def __init__(
        self,
        db_factory,
        ws_manager: ConnectionManager,
        minio_client: MinioClient | None = None,
        eink_renderer: EInkRenderer | None = None,
        voice_instructions: VoiceInstructionConfig | None = None,
        content_generation: Any = None,
        pipeline_executor: Any = None,
    ) -> None:
        self._db_factory = db_factory
        self._ws_manager = ws_manager
        self._minio = minio_client
        self._eink = eink_renderer
        self._voice = voice_instructions
        self._content_gen = content_generation
        self._pipeline_executor = pipeline_executor

    # -- info card delivery -------------------------------------------------

    async def deliver_info_card(
        self,
        card: InfoCard,
        *,
        channels: list[str],
        execution_id: int,
        rule_id: int | None = None,
        voice_instruction: str | None = None,
        speak: bool = False,
        dismiss_seconds: int = 60,
        eink_expiry_minutes: int = 30,
    ) -> DeliveryResult:
        """Broadcast info_card ws message, render eink, send voice prompt."""
        db: Session = self._db_factory()
        try:
            # Audit row
            delivery = InfoCardDelivery(
                info_card_id=card.id,
                rule_id=rule_id,
                execution_id=execution_id,
                channels=channels,
            )
            db.add(delivery)
            db.commit()
            db.refresh(delivery)
            delivery_id = delivery.id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        # Resolve voice instruction
        if self._voice:
            voice_inst = self._voice.compose(
                step_type="info_card",
                base_instruction="",
                step_override=voice_instruction or None,
                resource_override=card.voice_instruction or None,
            )
        else:
            voice_inst = voice_instruction or card.voice_instruction or ""

        # Build image slots for PWA
        image_slots: list[dict[str, Any]] = []
        if "pwa" in channels:
            for slot in card.image_slots or []:
                pwa_var = slot.variants.get("pwa", {}) if isinstance(slot.variants, dict) else {}
                object_name = pwa_var.get("object_name", slot.original_object_name)
                url = ""
                if object_name and self._minio:
                    try:
                        url = self._minio.generate_presigned_url(object_name)
                    except Exception:
                        logger.exception("presigned_url_failed", object_name=object_name)
                image_slots.append(
                    {
                        "slot_id": slot.slot_index,
                        "alt_text": slot.alt_text or "",
                        "url": url,
                        "width": pwa_var.get("width", 0),
                        "height": pwa_var.get("height", 0),
                    }
                )

        # PWA popup broadcast
        if "pwa" in channels:
            try:
                await self._ws_manager.broadcast(
                    {
                        "type": "info_card",
                        "delivery_id": delivery_id,
                        "layout_id": card.layout_id,
                        "title": card.title,
                        "body": card.body_text,
                        "image_slots": image_slots,
                        "dismiss_seconds": dismiss_seconds,
                        "server_timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            except Exception:
                logger.exception("info_card_ws_broadcast_failed")

        # Eink rendering
        if "eink" in channels and self._eink:
            try:
                # Resolve eink image variant from the first image slot
                eink_image_bytes: bytes | None = None
                for slot in card.image_slots or []:
                    variants = slot.variants if isinstance(slot.variants, dict) else {}
                    eink_var = variants.get("eink", {})
                    object_name = eink_var.get("object_name") or slot.original_object_name
                    if object_name and self._minio:
                        try:
                            eink_image_bytes = self._minio.get_object(object_name)
                        except Exception:
                            logger.exception("eink_image_fetch_failed", object_name=object_name)
                    break  # Use only the first image slot for eink

                await self._eink.render(
                    text=f"{card.title}\n\n{card.body_text}",
                    template="info_card",
                    expires_in_minutes=eink_expiry_minutes,
                    overlay_image=eink_image_bytes,
                )
            except Exception:
                logger.exception("info_card_eink_render_failed")

        # Voice delivery via Gemini Live (gated on explicit speak flag)
        if speak:
            try:
                voice_prompt = (
                    f"Here is some information for you.\n\n{card.title}\n\n{card.body_text}"
                )
                await self._ws_manager.send_backend_task(
                    prompt=voice_prompt,
                    voice_instruction=voice_inst or None,
                    metadata={
                        "delivery_type": "info_card",
                        "delivery_id": delivery_id,
                        "execution_id": execution_id,
                        "info_card_id": card.id,
                    },
                )
            except Exception:
                logger.exception("info_card_voice_delivery_failed")

        logger.info(
            "info_card_delivered",
            delivery_id=delivery_id,
            card_id=card.id,
            channels=channels,
        )
        return DeliveryResult(delivery_id=delivery_id)

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
                await self._ws_manager.send_backend_task(
                    prompt=voice_prompt,
                    voice_instruction=voice_inst or None,
                    metadata={
                        "delivery_type": "quiz_start",
                        "session_id": session_id,
                        "execution_id": execution_id,
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

    # -- info card events ---------------------------------------------------

    def record_info_card_event(self, delivery_id: int, action: str) -> InfoCardDelivery | None:
        """Update viewed_at or dismissed_at on the delivery audit row."""
        db: Session = self._db_factory()
        try:
            delivery = db.execute(
                select(InfoCardDelivery).where(InfoCardDelivery.id == delivery_id)
            ).scalar_one_or_none()
            if delivery is None:
                return None
            now = datetime.now(UTC)
            if action == "viewed":
                delivery.viewed_at = now
            elif action in ("dismissed", "timeout"):
                delivery.dismissed_at = now
                delivery.dismissed_by = "senior"
            db.commit()
            return delivery
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

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
            if execution_id and self._pipeline_executor:
                try:
                    db2: Session = self._db_factory()
                    try:
                        self._pipeline_executor.resume(execution_id, db2)
                    finally:
                        db2.close()
                except Exception:
                    logger.exception(
                        "quiz_complete_pipeline_resume_failed", execution_id=execution_id
                    )

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
        except Exception:
            db.rollback()
        finally:
            db.close()
