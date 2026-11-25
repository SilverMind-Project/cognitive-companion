"""Resident-facing session actions, split out of ``runtime.py`` to keep that
module under the package's 500-line guard.

None of these actions is
called back into by ``Runtime`` itself (unlike ``on_step_timeout``, which
``apply_decision`` schedules as a finalize callback and therefore stays in
``runtime.py``), so this module can depend one-directionally on
``Runtime.apply_decision``, ``Runtime.handle_completion``, and
``Presentation`` without creating a cycle.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Literal

from backend.core.exceptions import NotFoundError
from backend.core.logging import get_logger
from backend.models.guided_task import GuidedSession
from backend.observability.metrics import location_metrics as guided_metrics
from backend.services.guided_task.context import RuntimeContext
from backend.services.guided_task.domain import (
    STEP_IN_PROGRESS_STATUSES,
    TERMINAL_STATUSES,
    Decision,
)
from backend.services.guided_task.policy import resolve_policy
from backend.services.guided_task.presentation import Presentation
from backend.services.guided_task.state_machine import GuidedTaskStateMachine

logger = get_logger(__name__)

# Who reported a resident action: the voice agent (a tool call) or her own tap
# on the companion screen. Recorded on every event so the trail says which.
ActionSource = Literal["agent", "tablet"]
SurfaceAction = Literal["done", "repeat", "help"]

# Statuses in which a caregiver has already been called. Another request for
# help is recorded but neither re-notifies the caregiver nor leaves takeover.
_CAREGIVER_CALLED = frozenset({"escalated", "caregiver_takeover"})
# The metrics reason for a help tap (the agent passes its own reason).
TABLET_HELP_REASON = "resident_tapped_help"
# While escalated, another request for help pages the caregiver again only once
# this long has passed since they were last paged: rapid repeat taps never flood
# their phone, but a resident still waiting minutes later is heard again.
HELP_REPAGE_AFTER_S = 300


def _session_ended(status: str) -> dict:
    return {"acknowledged": False, "reason": "session_ended", "status": status}


class ResidentActions:
    """``repeat_step``, ``report_blocked``, ``request_help``, ``resume``, and the
    companion screen's ``surface_action``."""

    def __init__(
        self,
        ctx: RuntimeContext,
        presentation: Presentation,
        *,
        apply_decision: Callable[..., Awaitable[None]],
        handle_completion: Callable[..., Awaitable[dict]],
    ) -> None:
        self._ctx = ctx
        self._presentation = presentation
        self._apply_decision = apply_decision
        self._handle_completion = handle_completion

    async def surface_action(
        self, session_id: int, action: SurfaceAction, *, step_ord: int | None
    ) -> dict:
        """A tap on the resident's guided-task widget (I'm Done, Repeat, I Need Help).

        The caller holds the session lock. "Done" must name the step the screen
        showed: a tap on a screen that has not caught up is stale and ignored,
        so it can never complete a step she has not seen. "Repeat" and "help"
        are never refused as stale: she asks about whatever step she is on.
        """
        session = self._ctx.require_session(session_id)
        if session.status not in STEP_IN_PROGRESS_STATUSES:
            return {"accepted": False, "reason": "session_not_in_progress"}
        if action == "help":
            await self.request_help(session_id, TABLET_HELP_REASON, source="tablet")
            return {"accepted": True, "reason": None}
        if action == "repeat":
            await self.repeat_step(session_id, source="tablet", speak=True)
            return {"accepted": True, "reason": None}
        if session.status == "caregiver_takeover":
            # The caregiver is guiding her through the steps; only they advance.
            return {"accepted": False, "reason": "caregiver_takeover"}
        if step_ord is None or step_ord != session.current_step_ord:
            return {"accepted": False, "reason": "stale_step_completion"}
        result = await self._handle_completion(
            session_id,
            {"confirmed": True, "source": "tablet", "step_ord": step_ord},
            speak_on_advance=True,
        )
        return {"accepted": True, "reason": result.get("reason"), "advanced": result["advanced"]}

    async def repeat_step(
        self, session_id: int, *, source: ActionSource = "agent", speak: bool = False
    ) -> dict:
        """Record a repeat request; ``speak`` voices the step (the agent speaks it
        from the returned text itself, a tap has no agent turn)."""
        ctx = self._ctx
        now = ctx.now()
        session, routine, steps, step = ctx.load_runtime(session_id)
        if session.status in TERMINAL_STATUSES:
            return _session_ended(session.status)
        ctx.store.add_event(
            session_id=session.id,
            at=now,
            kind="step_repeated",
            step_ord=step.ord,
            actor="resident",
            detail={"source": source},
        )
        await self._presentation.broadcast_session_update(
            session, event_kind="step_repeated", actor="resident", detail=None, at=now
        )
        if speak:
            await self._presentation.speak(session, step, is_retry=False)
        descriptor = await self._presentation.step_descriptor(session, routine, steps, step)
        return {
            "step_ord": descriptor["step_ord"],
            "prompt_text": descriptor["prompt_text"],
        }

    async def report_blocked(
        self, session_id: int, reason: str, *, source: ActionSource = "agent"
    ) -> dict:
        ctx = self._ctx
        now = ctx.now()
        session, _routine, _steps, step = ctx.load_runtime(session_id)
        if session.status in TERMINAL_STATUSES:
            return _session_ended(session.status)
        detail = {"reason": reason, "source": source}
        ctx.store.add_event(
            session_id=session.id,
            at=now,
            kind="step_blocked",
            step_ord=step.ord,
            actor="resident",
            detail=detail,
        )
        await self._presentation.broadcast_session_update(
            session, event_kind="step_blocked", actor="resident", detail=detail, at=now
        )
        logger.info("guided_step_blocked", session_id=session.id, step_ord=step.ord)
        return {"acknowledged": True}

    async def request_help(
        self, session_id: int, reason: str | None = None, *, source: ActionSource = "agent"
    ) -> dict:
        """Escalate to a caregiver.

        An ended session is never reopened as escalated. During a takeover a
        caregiver is already with her, so another request is only recorded as
        ``help_repeated`` for the console and never leaves takeover. While
        escalated, a request within ``HELP_REPAGE_AFTER_S`` of the last page is
        recorded the same way; a later one pages the caregiver again.
        """
        ctx = self._ctx
        now = ctx.now()
        session, _routine, _steps, step = ctx.load_runtime(session_id)
        if session.status in TERMINAL_STATUSES:
            return _session_ended(session.status)
        help_reason = reason or "resident_requested"
        detail = {"reason": help_reason, "source": source}
        if session.status in _CAREGIVER_CALLED and not self._may_repage(session, now):
            ctx.store.add_event(
                session_id=session.id,
                at=now,
                kind="help_repeated",
                step_ord=step.ord,
                actor="resident",
                detail=detail,
            )
            await self._presentation.broadcast_session_update(
                session, event_kind="help_repeated", actor="resident", detail=detail, at=now
            )
            return {"acknowledged": True, "already_escalated": True}
        ctx.cancel_timeout(session.id)
        guided_metrics.guided_escalations_total.labels(kind="high").inc()
        ctx.store.update_session(session.id, status="escalated", last_activity_at=now)
        ctx.store.add_event(
            session_id=session.id,
            at=now,
            kind="help_requested",
            step_ord=step.ord,
            actor="resident",
            detail=detail,
        )
        updated = ctx.store.get_session(session.id)
        if updated is None:
            raise NotFoundError("Guided session", session.id)
        await ctx.escalator.escalate(session=updated, reason=help_reason, emergency=False)
        await self._presentation.broadcast_session_update(
            ctx.require_session(session.id),
            event_kind="help_requested",
            actor="resident",
            detail=detail,
            at=updated.last_activity_at,
        )
        logger.info("guided_help_requested", session_id=session.id, step_ord=step.ord)
        return {"acknowledged": True}

    def _may_repage(self, session: GuidedSession, now: datetime) -> bool:
        """Whether an escalated session's caregiver may be paged again now."""
        if session.status != "escalated":
            return False
        store = self._ctx.store
        paged = [
            at
            for kind in ("escalation", "help_requested")
            if (
                at := store.latest_event_at(
                    session_id=session.id, kind=kind, step_ord=None, any_step=True
                )
            )
            is not None
        ]
        return not paged or (now - max(paged)).total_seconds() >= HELP_REPAGE_AFTER_S

    async def resume(self, session_id: int) -> Decision:
        ctx = self._ctx
        now = ctx.now()
        session, routine, steps, step = ctx.load_runtime(session_id)
        decision = GuidedTaskStateMachine.decide(
            ctx.session_view(session, steps),
            ctx.step_view(step),
            "resume",
            resolve_policy(routine, step, ctx.settings),
            now,
        )
        await self._apply_decision(
            session=session,
            routine=routine,
            steps=steps,
            decision=decision,
            now=now,
            event_kind="retry" if decision.kind == "retry" else "session_abandoned",
            actor="system",
            detail={"reason": decision.reason},
        )
        return decision
