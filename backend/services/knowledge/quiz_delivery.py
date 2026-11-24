"""Quiz delivery: session start, completion, timeout, and question fanout.

Part of :class:`~backend.services.knowledge.delivery_service.KnowledgeDeliveryService`,
split out by responsibility; it shares that service's injected session factory,
WebSocket manager, MinIO client, voice instructions, grader, and scheduler.

The tablet (PWA) and the realtime voice agent are two views of one session. The
session row is the single source of truth: every answer, from either channel, goes
through :meth:`~backend.services.knowledge.quiz_answers.QuizAnswersMixin.submit_quiz_answer`,
which advances the row under a lock and then tells both views what comes next.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.core.exceptions import ValidationError
from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.models.knowledge import Quiz, QuizQuestion, QuizResponse, QuizSession
from backend.services.interactive_session import (
    WorkflowResumeScheduler,
    cancel_session_timeout,
    inject_session_prompt,
    resume_owning_pipeline,
    schedule_session_timeout,
    voice_owner_key,
)
from backend.services.knowledge.delivery_result import DeliveryResult
from backend.services.knowledge.quiz_answers import QuizAnswersMixin
from backend.services.knowledge.quiz_messages import (
    QUIZ_DELIVERY_TYPE,
    TERMINAL_QUIZ_STATUSES,
    question_descriptor,
    quiz_timeout_job_id,
    spoken_question,
)
from backend.services.knowledge.voice_instructions import QuizInteractionMode

# Logged under the delivery service's logger so existing log queries keep matching.
logger = get_logger("backend.services.knowledge.delivery_service")


class QuizDeliveryMixin(QuizAnswersMixin):
    """Quiz session lifecycle over the PWA WebSocket and realtime voice."""

    _db_factory: Callable[[], Session]
    _minio: MinioClient | None
    _content_gen: Any
    _scheduler: WorkflowResumeScheduler | None
    # Sessions whose prompts went to the realtime agent. Answers tapped on the tablet
    # for these are relayed to the agent; a tablet-only quiz never opens a paid
    # realtime session. In memory: a restart also ends every realtime session.
    _voice_sessions: set[int]

    # -- start ---------------------------------------------------------------

    async def start_quiz_session(
        self,
        quiz: Quiz,
        *,
        execution_id: int,
        rule_id: int | None = None,
        channels: list[str] | None = None,
        voice_instruction: str | None = None,
        max_questions: int = 5,
        randomize_order: bool = False,
        session_timeout_minutes: int = 10,
        interaction_mode: QuizInteractionMode = "gentle",
        senior_id: str | None = None,
        template_data: Mapping[str, Any] | None = None,
        trigger_vars: Mapping[str, Any] | None = None,
        surface_id: str | None = None,
    ) -> DeliveryResult:
        """Create the session, show question 1 on the tablet, and ask it aloud.

        Raises ``ValidationError`` for a quiz with no questions, before any session row
        is written. Schedules the session timeout; the result's ``timeout_at`` is when
        an unfinished session becomes ``timed_out`` and its pipeline resumes.
        ``surface_id`` is the companion surface in her room: every message of the
        session goes there (every screen when None), and it holds the microphone
        until the session ends.
        """
        channels = list(channels or ["pwa", "voice"])
        questions = sorted(quiz.questions or [], key=lambda q: q.ord)
        if randomize_order:
            random.shuffle(questions)
        questions = questions[:max_questions]
        if not questions:
            raise ValidationError(f"Quiz {quiz.id} has no questions to ask")
        total = len(questions)
        first = questions[0]

        db: Session = self._db_factory()
        try:
            session = QuizSession(
                quiz_id=quiz.id,
                rule_id=rule_id,
                execution_id=execution_id,
                senior_id=senior_id,
                status="started",
                question_order=[q.id for q in questions],
            )
            db.add(session)
            db.commit()
            session_id = session.id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        timeout_at = datetime.now(UTC) + timedelta(minutes=session_timeout_minutes)
        schedule_session_timeout(
            self._scheduler,
            job_id=quiz_timeout_job_id(session_id),
            run_at=timeout_at,
            finalize=self.handle_session_timeout,
            args=[session_id],
        )

        context = self._template_context(template_data, trigger_vars, senior_id)
        intro = self._render(quiz.intro_voice_template or "", context)
        speak = "voice" in channels
        await self._engage_resident_surface(
            voice_owner_key(QUIZ_DELIVERY_TYPE, session_id),
            surface_id,
            reason=QUIZ_DELIVERY_TYPE,
            turn_seconds=session_timeout_minutes * 60,
            microphone=speak,
        )

        if "pwa" in channels:
            try:
                await self._send_to_resident(
                    voice_owner_key(QUIZ_DELIVERY_TYPE, session_id),
                    {
                        "type": "quiz_start",
                        "session_id": session_id,
                        "quiz_id": quiz.id,
                        "title": self._render(quiz.title, context),
                        "intro_voice_text": intro,
                        "total_questions": total,
                        "interaction_mode": interaction_mode,
                        "voice": speak,
                    },
                )
                await self._send_question_ws(session_id, first, 0, total, interaction_mode)
            except Exception:
                logger.exception("quiz_start_ws_broadcast_failed", session_id=session_id)

        if speak:
            await self._speak_quiz_start(
                quiz,
                session_id=session_id,
                execution_id=execution_id,
                first=first,
                total=total,
                intro=intro,
                voice_instruction=voice_instruction,
                interaction_mode=interaction_mode,
                context=context,
            )

        logger.info(
            "quiz_session_started",
            session_id=session_id,
            quiz_id=quiz.id,
            question_count=total,
            interaction_mode=interaction_mode,
            voice=speak,
        )
        return DeliveryResult(session_id=session_id, timeout_at=timeout_at)

    async def _speak_quiz_start(
        self,
        quiz: Quiz,
        *,
        session_id: int,
        execution_id: int,
        first: QuizQuestion,
        total: int,
        intro: str,
        voice_instruction: str | None,
        interaction_mode: QuizInteractionMode,
        context: Mapping[str, Any],
    ) -> None:
        directive = self._voice.quiz_mode_directive(interaction_mode) if self._voice else ""
        composed = self._compose_voice(
            "quiz",
            step_override=voice_instruction,
            resource_override=quiz.voice_instruction,
            context=context,
            directive=directive,
        )
        opening = intro or f"Let's chat about {quiz.title}."
        prompt = f"{opening} There are {total} questions. {spoken_question(session_id, first, 0)}"
        try:
            # The senior answers aloud, so the tablet microphone must be live before
            # the question is spoken; an idle tablet would otherwise hear nothing.
            await self._send_to_resident(
                voice_owner_key(QUIZ_DELIVERY_TYPE, session_id),
                {
                    "type": "enable_microphone",
                    "reason": "quiz_voice",
                    "session_id": session_id,
                },
            )
            await inject_session_prompt(
                self._ws_manager,
                prompt=prompt,
                delivery_type=QUIZ_DELIVERY_TYPE,
                session_id=session_id,
                execution_id=execution_id,
                voice_instruction=composed or None,
                extra_metadata={"quiz_id": quiz.id},
                surface_id=self._resident_surface(voice_owner_key(QUIZ_DELIVERY_TYPE, session_id)),
            )
        except Exception:
            logger.exception("quiz_voice_delivery_failed", session_id=session_id)
            return
        self._voice_sessions.add(session_id)
        self._mark_in_progress(session_id)

    # -- reads ---------------------------------------------------------------

    def get_current_question(self, session_id: int) -> dict[str, Any]:
        """Return the question the senior should answer next.

        Returns ord, text, type, choices, or {"done": True} if the session is over.
        """
        db: Session = self._db_factory()
        try:
            session = db.get(QuizSession, session_id)
            if session is None:
                return {"error": "Session not found"}
            if session.status in TERMINAL_QUIZ_STATUSES:
                return {"done": True, "reason": session.status}

            question_order: list[int] = session.question_order or []
            total = len(question_order)
            idx = session.current_question_ord
            if total == 0 or idx >= total:
                return {"done": True, "reason": "past last question"}

            question = db.get(QuizQuestion, question_order[idx])
            if question is None:
                return {"done": True, "reason": "question not found"}
            return {"session_id": session_id, **question_descriptor(question, idx, total)}
        finally:
            db.close()

    # -- terminal transitions -------------------------------------------------

    async def complete_quiz_session(self, session_id: int) -> dict[str, Any]:
        """Finalize a quiz session; repeating it on a finished session changes nothing."""
        db: Session = self._db_factory()
        try:
            session = db.execute(
                select(QuizSession).where(QuizSession.id == session_id).with_for_update()
            ).scalar_one_or_none()
            if session is None:
                return {"error": "Session not found"}
            responses = (
                db.execute(select(QuizResponse).where(QuizResponse.session_id == session_id))
                .scalars()
                .all()
            )
            num_answered = len(responses)
            num_correct = sum(1 for r in responses if r.is_correct)
            if session.status in TERMINAL_QUIZ_STATUSES:
                return {
                    "session_id": session_id,
                    "status": session.status,
                    "num_correct": num_correct,
                    "num_answered": num_answered,
                }
            session.status = "completed"
            session.completed_at = datetime.now(UTC)
            execution_id = session.execution_id
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        cancel_session_timeout(self._scheduler, job_id=quiz_timeout_job_id(session_id))
        try:
            await self._send_to_resident(
                voice_owner_key(QUIZ_DELIVERY_TYPE, session_id),
                {
                    "type": "quiz_complete",
                    "session_id": session_id,
                    "num_correct": num_correct,
                    "num_answered": num_answered,
                },
            )
        except Exception:
            logger.exception("quiz_complete_broadcast_failed", session_id=session_id)
        await self._end_session_side_effects(session_id, execution_id)

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

    async def handle_session_timeout(self, session_id: int) -> None:
        """Scheduler callback: time out a session that is still open.

        A session that already finished is left alone, so a timeout job that fires
        after completion can never overwrite ``completed``.
        """
        db: Session = self._db_factory()
        try:
            session = db.execute(
                select(QuizSession).where(QuizSession.id == session_id).with_for_update()
            ).scalar_one_or_none()
            if session is None or session.status in TERMINAL_QUIZ_STATUSES:
                db.rollback()
                return
            session.status = "timed_out"
            session.completed_at = datetime.now(UTC)
            execution_id = session.execution_id
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("quiz_session_timeout_failed", session_id=session_id)
            return
        finally:
            db.close()

        try:
            await self._send_to_resident(
                voice_owner_key(QUIZ_DELIVERY_TYPE, session_id),
                {"type": "quiz_timeout", "session_id": session_id},
            )
        except Exception:
            logger.exception("quiz_timeout_broadcast_failed", session_id=session_id)
        await self._end_session_side_effects(session_id, execution_id)
        logger.info("quiz_session_timed_out", session_id=session_id)

    async def _end_session_side_effects(self, session_id: int, execution_id: int | None) -> None:
        """Drop the quiz persona, hand back the surface, and resume the parked pipeline."""
        self._voice_sessions.discard(session_id)
        await self._release_resident(
            voice_owner_key(QUIZ_DELIVERY_TYPE, session_id), reason=QUIZ_DELIVERY_TYPE
        )
        resume_owning_pipeline(self._scheduler, execution_id)

    # -- helpers ---------------------------------------------------------------

    def _mark_in_progress(self, session_id: int) -> None:
        """``started`` -> ``in_progress`` only; never touches a session that has ended."""
        db: Session = self._db_factory()
        try:
            db.execute(
                update(QuizSession)
                .where(QuizSession.id == session_id, QuizSession.status == "started")
                .values(status="in_progress")
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("quiz_mark_in_progress_failed", session_id=session_id)
        finally:
            db.close()

    async def _send_question_ws(
        self,
        session_id: int,
        question: QuizQuestion,
        ord_num: int,
        total: int,
        interaction_mode: QuizInteractionMode | None,
    ) -> None:
        """Send a quiz_question ws message (with the explanation, used as a gentle hint)."""
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

        payload: dict[str, Any] = {
            "type": "quiz_question",
            "session_id": session_id,
            **question_descriptor(question, ord_num, total),
            "hint": question.explanation or "",
            "image": image_data,
            "server_timestamp": datetime.now(UTC).isoformat(),
        }
        if interaction_mode is not None:
            payload["interaction_mode"] = interaction_mode
        await self._send_to_resident(voice_owner_key(QUIZ_DELIVERY_TYPE, session_id), payload)
