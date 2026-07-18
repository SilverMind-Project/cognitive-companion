"""Caregiver takeover surface (M29).

Depends on ``runtime.py`` (``complete``, ``apply_decision``) and
``presentation.py`` (``broadcast_session_update``, ``session_out``,
``advance_descriptor``), both already-built collaborators injected by the
façade.
"""

from __future__ import annotations

from backend.core.exceptions import NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.models.guided_task import GuidedSession, Routine
from backend.schemas.guided_task import GuidedSessionOut
from backend.services.guided_task.agent_voice import GUIDED_TASK_DELIVERY_TYPE
from backend.services.guided_task.context import RuntimeContext
from backend.services.guided_task.language import compose_language_directive
from backend.services.guided_task.policy import resolve_policy
from backend.services.guided_task.presentation import Presentation
from backend.services.guided_task.runtime import Runtime
from backend.services.guided_task.state_machine import GuidedTaskStateMachine
from backend.services.interactive_session.prompt_injection import inject_session_prompt

logger = get_logger(__name__)


class Caregiver:
    """Caregiver takeover: begin/say/advance/complete/release."""

    def __init__(
        self,
        ctx: RuntimeContext,
        runtime: Runtime,
        presentation: Presentation,
    ) -> None:
        self._ctx = ctx
        self._runtime = runtime
        self._presentation = presentation

    async def begin_takeover(self, session_id: int) -> GuidedSessionOut:
        ctx = self._ctx
        now = ctx.now()
        session, routine, steps, step = ctx.load_runtime(session_id)
        if session.status not in {"active", "waiting", "escalated"}:
            raise ValidationError("Guided session cannot enter caregiver takeover")
        decision = GuidedTaskStateMachine.decide(
            ctx.session_view(session, steps),
            ctx.step_view(step),
            "caregiver_takeover",
            resolve_policy(routine, step, ctx.settings),
            now,
        )
        await self._runtime.apply_decision(
            session=session,
            routine=routine,
            steps=steps,
            decision=decision,
            now=now,
            event_kind="caregiver_takeover",
            actor="caregiver",
            detail={"reason": decision.reason},
        )
        updated = ctx.require_session(session.id)
        await self._presentation.broadcast_session_update(
            updated,
            event_kind="takeover_started",
            actor="caregiver",
            detail={"reason": decision.reason},
            at=now,
        )
        logger.info("guided_takeover_started", session_id=session.id, step_ord=step.ord)
        return self._presentation.session_out(updated)

    async def caregiver_say(self, session_id: int, text: str) -> GuidedSessionOut:
        ctx = self._ctx
        now = ctx.now()
        session, routine, _steps, step = ctx.load_runtime(session_id)
        if session.status not in {"escalated", "caregiver_takeover"}:
            raise ValidationError("Caregiver messages require escalation or takeover")
        clean_text = text.strip()
        if not clean_text:
            raise ValidationError("Caregiver message cannot be empty")

        conversation_manager = ctx.conversation_manager
        if conversation_manager is not None:
            conversation_session_id = session.conversation_session_id
            if conversation_session_id is None:
                conversation_session_id = conversation_manager.create_session()
                session = ctx.link_conversation(
                    session, conversation_session_id, now=now, actor="system"
                )
            conversation_manager.add_turn(
                conversation_session_id,
                "caregiver",
                clean_text,
                metadata={"guided_session_id": session.id, "routine_id": session.routine_id},
            )

        ctx.store.add_event(
            session_id=session.id,
            at=now,
            kind="caregiver_message",
            step_ord=step.ord,
            actor="caregiver",
            detail={"text": clean_text},
        )
        updated = ctx.store.update_session(session.id, last_activity_at=now)
        if updated is None:
            raise NotFoundError("Guided session", session.id)

        await self.inject_caregiver_message(updated, routine, clean_text)
        await self._presentation.broadcast_session_update(
            updated,
            event_kind="caregiver_message",
            actor="caregiver",
            detail={"step_ord": step.ord},
            at=now,
        )
        logger.info("guided_caregiver_say", session_id=session.id, step_ord=step.ord)
        return self._presentation.session_out(updated)

    async def caregiver_advance(self, session_id: int) -> dict:
        ctx = self._ctx
        now = ctx.now()
        session, routine, steps, step = ctx.load_runtime(session_id)
        if session.status not in {"escalated", "caregiver_takeover"}:
            raise ValidationError("Caregiver advance requires escalation or takeover")
        decision = GuidedTaskStateMachine.decide(
            ctx.session_view(session, steps),
            ctx.step_view(step),
            "step_completed",
            resolve_policy(routine, step, ctx.settings),
            now,
            evidence={"confirmed": True, "source": "caregiver"},
        )
        ctx.store.add_event(
            session_id=session.id,
            at=now,
            kind="step_completed",
            step_ord=step.ord,
            actor="caregiver",
            detail={"confirmed": True, "source": "caregiver"},
        )
        if decision.kind == "complete":
            await self._runtime.complete(session.id, "escalated_resolved", actor="caregiver")
        elif decision.kind in {"advance", "skip"}:
            updated_step = ctx.step_by_ord(steps, decision.next_step_ord)
            ctx.store.update_session(
                session.id,
                status="caregiver_takeover",
                current_step_ord=decision.next_step_ord,
                attempts=decision.attempts,
                last_activity_at=now,
            )
            ctx.store.add_event(
                session_id=session.id,
                at=now,
                kind="step_entered",
                step_ord=updated_step.ord,
                actor="caregiver",
                detail={"source": "caregiver"},
            )
        elif decision.kind == "wait":
            return self._presentation.decision_descriptor(decision)
        updated = ctx.require_session(session.id)
        await self._presentation.broadcast_session_update(
            updated,
            event_kind="step_completed",
            actor="caregiver",
            detail={"source": "caregiver"},
            at=now,
        )
        return await self._presentation.advance_descriptor(session.id, routine, steps, decision)

    async def caregiver_complete(self, session_id: int) -> GuidedSessionOut:
        updated = await self._runtime.complete(session_id, "escalated_resolved", actor="caregiver")
        await self._presentation.broadcast_session_update(
            updated,
            event_kind="session_completed",
            actor="caregiver",
            detail={"outcome": "escalated_resolved"},
            at=updated.last_activity_at,
        )
        return self._presentation.session_out(updated)

    async def release_takeover(self, session_id: int) -> GuidedSessionOut:
        ctx = self._ctx
        now = ctx.now()
        session, routine, _steps, step = ctx.load_runtime(session_id)
        if session.status != "caregiver_takeover":
            raise ValidationError("Guided session is not in caregiver takeover")
        updated = ctx.store.update_session(session.id, status="active", last_activity_at=now)
        if updated is None:
            raise NotFoundError("Guided session", session.id)
        ctx.store.add_event(
            session_id=session.id,
            at=now,
            kind="takeover_ended",
            step_ord=step.ord,
            actor="caregiver",
            detail={"status": "active"},
        )
        ctx.schedule_timeout(updated, routine, step, now, finalize=self._runtime.on_step_timeout)
        await self._presentation.broadcast_session_update(
            updated,
            event_kind="takeover_ended",
            actor="caregiver",
            detail={"status": "active"},
            at=now,
        )
        return self._presentation.session_out(updated)

    async def inject_caregiver_message(
        self,
        session: GuidedSession,
        routine: Routine,
        text: str,
    ) -> None:
        ctx = self._ctx
        ws_manager = ctx.ws_manager
        if ws_manager is None:
            logger.warning(
                "guided_caregiver_say_skipped",
                session_id=session.id,
                reason="ws_manager_unavailable",
            )
            return
        resident_name = ctx.resident_name(session.person_id)
        prompt = (
            f"Tell {resident_name} the following, in her language and in your own warm voice, "
            f"as if it is your idea: {text}"
        )
        voice_instruction = routine.system_instruction_override or None
        directive = compose_language_directive(
            ctx.settings, ctx.voice_instructions, routine.language_override
        )
        if directive:
            voice_instruction = f"{voice_instruction}\n\n{directive}" if voice_instruction else directive
        await inject_session_prompt(
            ws_manager,
            prompt=prompt,
            delivery_type=GUIDED_TASK_DELIVERY_TYPE,
            session_id=session.id,
            execution_id=session.execution_id,
            voice_instruction=voice_instruction,
            extra_metadata={"actor": "caregiver", "caregiver_text_hidden": True},
        )
