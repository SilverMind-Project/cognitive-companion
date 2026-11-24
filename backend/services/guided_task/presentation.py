"""Rendering, descriptors, and websocket payloads for guided sessions (M29).

Leaf module: depends only on ``RuntimeContext``, never on ``runtime.py``,
``summon.py``, ``watch.py``, or ``caregiver.py``. Those modules call back
into this one's public methods (``step_descriptor``, ``advance_descriptor``,
``decision_descriptor``, ``speak``, ``session_out``,
``broadcast_session_update``) to render output and dispatch voice/WS
updates without duplicating that logic.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

from backend.core.exceptions import NotFoundError
from backend.core.logging import get_logger
from backend.core.template import render_template
from backend.models.guided_task import GuidedSession, Routine, RoutineStep
from backend.schemas.guided_task import (
    GuidedSessionDetailOut,
    GuidedSessionEventOut,
    GuidedSessionListOut,
    GuidedSessionOut,
    GuidedSessionStepOut,
    GuidedSessionTurnOut,
)
from backend.schemas.guided_task_ws import GuidedSessionStateEvent, GuidedSessionUpdateEvent
from backend.services.guided_task import surface_lease
from backend.services.guided_task.agent_voice import GUIDED_TASK_DELIVERY_TYPE
from backend.services.guided_task.context import RuntimeContext
from backend.services.guided_task.domain import STEP_IN_PROGRESS_STATUSES, Decision
from backend.services.interactive_session.tagging import voice_owner_key

logger = get_logger(__name__)


class Presentation:
    """Descriptor rendering, session detail/list reads, and WS broadcast."""

    def __init__(self, ctx: RuntimeContext) -> None:
        self._ctx = ctx

    def session_out(self, session: GuidedSession) -> GuidedSessionOut:
        return GuidedSessionOut.model_validate(session, from_attributes=True)

    async def get_detail(self, session_id: int) -> GuidedSessionDetailOut:
        ctx = self._ctx
        session = ctx.store.get_session(session_id)
        if session is None:
            raise NotFoundError("Guided session", session_id)
        routine, steps = ctx.load_routine_steps(session.routine_id)
        current_step: GuidedSessionStepOut | None = None
        if steps:
            step = ctx.step_by_ord(steps, session.current_step_ord)
            current_step = GuidedSessionStepOut(
                ord=step.ord,
                prompt_text=await self._render_step_prompt(session, routine, step),
                completion_gate=step.completion_gate,
                is_safety_critical=step.is_safety_critical,
            )
        events = [
            GuidedSessionEventOut.model_validate(event, from_attributes=True)
            for event in ctx.store.list_events(session_id=session.id, limit=20)
        ]
        recent_transcript: list[GuidedSessionTurnOut] = []
        conversation_manager = ctx.conversation_manager
        if conversation_manager is not None and session.conversation_session_id is not None:
            recent_transcript = [
                GuidedSessionTurnOut(**turn)
                for turn in conversation_manager.get_recent_turns(
                    session.conversation_session_id, limit=10
                )
            ]
        elif conversation_manager is not None:
            logger.warning("guided_detail_transcript_unlinked", session_id=session.id)
        return GuidedSessionDetailOut(
            session=self.session_out(session),
            current_step=current_step,
            recent_events=events,
            recent_transcript=recent_transcript,
        )

    async def get_active_step(self, session_id: int) -> dict:
        from backend.core.exceptions import ValidationError

        ctx = self._ctx
        session = ctx.store.get_session(session_id)
        if session is None:
            raise NotFoundError("Guided session", session_id)
        if session.status == "completed":
            return {"done": True}
        routine, steps = ctx.load_routine_steps(session.routine_id)
        if not steps:
            raise ValidationError("Routine has no steps")
        step = ctx.step_by_ord(steps, session.current_step_ord)
        return await self.step_descriptor(session, routine, steps, step)

    def list_sessions(
        self,
        *,
        person_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> GuidedSessionListOut:
        rows, total = self._ctx.store.list_sessions(
            person_id=person_id, status=status, limit=limit, offset=offset
        )
        return GuidedSessionListOut(
            items=[self.session_out(s) for s in rows],
            total=total,
        )

    async def speak(
        self,
        session: GuidedSession,
        step: RoutineStep,
        *,
        is_retry: bool,
        prefix: str | None = None,
    ) -> None:
        ctx = self._ctx
        routine = ctx.store.get_routine(session.routine_id)
        if routine is None:
            raise NotFoundError("Routine", session.routine_id)
        rendered = await self._render_step_prompt(session, routine, step)
        if prefix:
            rendered = f"{prefix} {rendered}"
        voice_session = SimpleNamespace(
            id=session.id,
            routine_id=session.routine_id,
            person_id=session.person_id,
            execution_id=session.execution_id,
            surface_id=session.surface_id,
            status=session.status,
            current_step_ord=session.current_step_ord,
            attempts=session.attempts,
            routine_system_instruction_override=routine.system_instruction_override,
            resident_name=ctx.resident_name(session.person_id),
            total_steps=len(ctx.store.list_steps(session.routine_id)),
            language_override=routine.language_override,
            voice_override=routine.voice_override,
            capture_lease_s=surface_lease.step_lease_seconds(ctx, routine, step),
        )
        await ctx.voice.speak_step(
            session=voice_session,
            step=step,
            rendered_prompt=rendered,
            is_retry=is_retry,
        )

    async def release_resident(self, session_id: int) -> None:
        """Hand the resident's surface back once a session has ended.

        Restores the companion's base persona (owner-keyed, so it only clears an
        instruction this session set and never strips a quiz or info card that has
        since taken over the realtime voice) and closes the microphone lease on the
        session's surface.
        """
        ws_manager = self._ctx.ws_manager
        if ws_manager is None:
            return
        await ws_manager.release_voice_instruction(
            voice_owner_key(GUIDED_TASK_DELIVERY_TYPE, session_id)
        )
        await surface_lease.release(self._ctx, session_id)

    async def step_descriptor(
        self,
        session: GuidedSession,
        routine: Routine,
        steps: list[RoutineStep],
        step: RoutineStep,
    ) -> dict:
        return {
            "step_ord": step.ord,
            "total": len(steps),
            "prompt_text": await self._render_step_prompt(session, routine, step),
            "is_retry": session.attempts > 0,
        }

    async def advance_descriptor(
        self,
        session_id: int,
        routine: Routine,
        steps: list[RoutineStep],
        decision: Decision,
    ) -> dict:
        """Build the caller-facing advance/done/next_step descriptor.

        Re-reads the session rather than trusting ``decision.next_step_ord``
        directly: an entry-time skip_condition (G4) can cascade past the step
        ``decision`` names, including all the way to completion, after
        ``_apply_decision`` already dispatched further skips for the landed
        step.
        """
        ctx = self._ctx
        base = self.decision_descriptor(decision)
        if decision.kind not in {"advance", "skip", "complete"}:
            return base
        updated = ctx.store.get_session(session_id)
        if updated is None:
            raise NotFoundError("Guided session", session_id)
        if updated.status == "completed":
            base.update({"advanced": True, "done": True, "next_step": None})
            return base
        next_step = ctx.step_by_ord(steps, updated.current_step_ord)
        base.update(
            {
                "advanced": True,
                "done": False,
                "next_step": await self.step_descriptor(updated, routine, steps, next_step),
            }
        )
        return base

    def decision_descriptor(self, decision: Decision) -> dict:
        if decision.kind == "wait":
            return {"advanced": False, "reason": decision.reason}
        if decision.kind == "noop":
            return {"advanced": False, "reason": decision.reason}
        return {
            "advanced": decision.kind in {"advance", "skip", "complete"},
            "done": decision.kind == "complete",
            "reason": decision.reason,
            "next_step": None,
        }

    async def broadcast_session_update(
        self,
        session: GuidedSession,
        *,
        event_kind: str,
        actor: str | None,
        detail: dict | None,
        at: Any,
    ) -> None:
        """Announce a session transition to the caregiver console and the tablet.

        The console event (``/ws/pipeline``) carries the full diagnostic detail.
        The companion socket (``/ws/audio``) only ever receives the resident-safe
        ``guided_session_state`` built by :meth:`broadcast_resident_state`.

        Best-effort: the transition is already written when this runs, so a
        failure here is logged and never raised into the caller (an agent tool
        call, a scheduled timeout, or the watch tick).
        """
        try:
            await self._broadcast(session, event_kind=event_kind, actor=actor, detail=detail, at=at)
        except Exception:
            logger.exception(
                "guided_broadcast_failed", session_id=session.id, event_kind=event_kind
            )

    async def _broadcast(
        self,
        session: GuidedSession,
        *,
        event_kind: str,
        actor: str | None,
        detail: dict | None,
        at: Any,
    ) -> None:
        ctx = self._ctx
        event = GuidedSessionUpdateEvent(
            session_id=session.id,
            routine_id=session.routine_id,
            person_id=session.person_id,
            status=session.status,
            current_step_ord=session.current_step_ord,
            event_kind=event_kind,
            actor=actor,
            detail=detail,
            at=at,
        )
        if ctx.admin_ws_broadcaster is not None:
            await ctx.admin_ws_broadcaster(event.model_dump(mode="json"))
        await self.broadcast_resident_state(session, at=at)

    async def broadcast_resident_state(self, session: GuidedSession, *, at: Any) -> None:
        ctx = self._ctx
        if ctx.ws_manager is None:
            return
        event = await self.resident_state(session, at=at)
        await ctx.ws_manager.send_to_surface(session.surface_id, event.model_dump(mode="json"))
        if session.status in STEP_IN_PROGRESS_STATUSES:
            await surface_lease.renew(ctx, session)

    async def current_resident_state(
        self, person_id: str | None = None, *, surface_id: str | None = None
    ) -> GuidedSessionStateEvent | None:
        """The resident-safe state of the newest session with a step in progress.

        Only one session per person can be live, so with ``person_id`` there is
        at most one. A summoning session is left out: its step has not been put
        to her, so her screen has nothing to show yet. ``surface_id`` is the
        reading screen: it sees the sessions the live broadcast would reach it with.
        """
        ctx = self._ctx
        sessions = [
            s
            for s in ctx.store.list_live_sessions()
            if s.status in STEP_IN_PROGRESS_STATUSES
            and (person_id is None or s.person_id == person_id)
            and self._shown_on(s, surface_id)
        ]
        if not sessions:
            return None
        session = max(sessions, key=lambda s: (s.started_at, s.id))
        return await self.resident_state(session, at=ctx.now())

    def _shown_on(self, session: GuidedSession, viewer_surface_id: str | None) -> bool:
        """Whether ``broadcast_resident_state`` reaches the screen ``viewer_surface_id``.

        Mirrors ``send_to_surface``: a session goes to its own surface while that
        surface is connected, and to every screen when it has none or it is offline.
        """
        target = session.surface_id
        if target is None or target == viewer_surface_id:
            return True
        ws_manager = self._ctx.ws_manager
        return ws_manager is None or not ws_manager.is_surface_connected(target)

    async def resident_state(self, session: GuidedSession, *, at: Any) -> GuidedSessionStateEvent:
        """The resident-safe view of ``session``: what her screen may show.

        One builder for the live broadcast and the tablet's hydration read, so a
        tablet that reconnects mid-routine shows exactly what a broadcast would.
        """
        ctx = self._ctx
        routine, steps = ctx.load_routine_steps(session.routine_id)
        prompt_text = ""
        if session.status in STEP_IN_PROGRESS_STATUSES and steps:
            step = ctx.step_by_ord(steps, session.current_step_ord)
            prompt_text = await self._render_step_prompt(
                session, routine, step, include_agent_context=False
            )
        return GuidedSessionStateEvent(
            session_id=session.id,
            routine_id=session.routine_id,
            routine_name=routine.name,
            person_id=session.person_id,
            status=session.status,
            current_step_ord=session.current_step_ord,
            total_steps=len(steps),
            prompt_text=prompt_text,
            at=at,
        )

    async def _render_step_prompt(
        self,
        session: GuidedSession,
        routine: Routine,
        step: RoutineStep,
        *,
        include_agent_context: bool = True,
    ) -> str:
        """Render a step prompt.

        ``memory_context`` and ``preferences`` are context for the agent (for
        example how the routine went last time); they are left blank when the
        text is for the resident's screen.
        """
        memory_context = ""
        preferences: list[str] = []
        if include_agent_context:
            memory_context = await self._memory_context(session, routine)
            preferences = self._preferences(session.person_id)
        return render_template(
            step.prompt_template,
            {
                "session": {
                    "id": session.id,
                    "person_id": session.person_id,
                    "current_step_ord": session.current_step_ord,
                },
                "routine": {"id": routine.id, "name": routine.name},
                "step": {"ord": step.ord},
                "memory_context": memory_context,
                "preferences": preferences,
            },
        )

    def _preferences(self, person_id: str) -> list[str]:
        """Top 3 durable resident preferences, shortest-first (DL-M05 Part E.2).

        Best-effort: a lookup failure degrades to no preferences rather than
        blocking prompt rendering.
        """
        knowledge_ingestion = self._ctx.knowledge_ingestion
        if knowledge_ingestion is None:
            return []
        try:
            docs = knowledge_ingestion.list_documents_by_tags(
                ["resident_preference", person_id], limit=20
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "guided_preferences_unavailable",
                person_id=person_id,
                error=str(exc),
            )
            return []
        texts = sorted((doc.source_text for doc in docs), key=len)
        return texts[:3]

    async def _memory_context(self, session: GuidedSession, routine: Routine) -> str:
        """Compose the prompt's memory context: recent scene context (fuzzy)
        plus, when available, one sentence recalling the last time this
        routine ran (DL-M05 Part E.1). Single seam: no second prompt-compose
        hook is added for the episode read-back.
        """
        memory_query = self._ctx.memory_query
        if memory_query is None:
            return ""
        try:
            hits = await memory_query.search(
                room_id=None,
                since_minutes=None,
                objects_any=(routine.name,),
                kind="guided_episode",
                person_id=session.person_id,
                limit=1,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "guided_memory_context_unavailable",
                session_id=session.id,
                error=str(exc),
            )
            return ""
        if not hits:
            return ""
        return _condense_episode_sentence(hits[0].description)


_OUTCOME_RE = re.compile(r"ended with outcome '([^']+)'")
_DURATION_RE = re.compile(r"Duration (\d+) seconds")
_RETRY_RE = re.compile(r"step (\d+) retried (\d+)x")


def _condense_episode_sentence(description: str) -> str:
    """Condense an episode's deterministic multi-sentence summary (built by
    ``memory_bridge.build_episode_description``) into one prompt sentence.
    Hard-capped at one sentence: the prompt is per-session token cost.
    """
    if not description:
        return ""
    outcome_match = _OUTCOME_RE.search(description)
    duration_match = _DURATION_RE.search(description)
    if outcome_match is None or duration_match is None:
        # Format doesn't match the bridge's template (e.g. a legacy or
        # hand-written observation); fall back to a bounded raw prefix.
        return f"Last time this routine: {description[:160].rstrip()}"
    outcome = outcome_match.group(1)
    minutes = max(1, int(duration_match.group(1)) // 60)
    plural = "" if minutes == 1 else "s"
    sentence = f"Last time this routine: {outcome} in {minutes} minute{plural}"
    retry_match = _RETRY_RE.search(description)
    if retry_match:
        sentence += f"; step {retry_match.group(1)} needed {retry_match.group(2)} tries"
    return sentence + "."
