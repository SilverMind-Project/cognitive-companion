"""Simple resident-facing session actions (M29), split out of ``runtime.py``
to keep that module under the package's 500-line guard.

These four actions share no state with each other and none of them is
called back into by ``Runtime`` itself (unlike ``on_step_timeout``, which
``apply_decision`` schedules as a finalize callback and therefore stays in
``runtime.py``), so this module can depend one-directionally on
``Runtime.apply_decision`` and ``Presentation.step_descriptor`` without
creating a cycle.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from backend.core.exceptions import NotFoundError
from backend.core.logging import get_logger
from backend.services.guided_task.context import RuntimeContext
from backend.services.guided_task.domain import Decision
from backend.services.guided_task.policy import resolve_policy
from backend.services.guided_task.presentation import Presentation
from backend.services.guided_task.state_machine import GuidedTaskStateMachine

logger = get_logger(__name__)


class ResidentActions:
    """``repeat_step``, ``report_blocked``, ``request_help``, ``resume``."""

    def __init__(
        self,
        ctx: RuntimeContext,
        presentation: Presentation,
        *,
        apply_decision: Callable[..., Awaitable[None]],
    ) -> None:
        self._ctx = ctx
        self._presentation = presentation
        self._apply_decision = apply_decision

    async def repeat_step(self, session_id: int) -> dict:
        ctx = self._ctx
        session, routine, steps, step = ctx.load_runtime(session_id)
        ctx.store.add_event(
            session_id=session.id,
            at=ctx.now(),
            kind="step_repeated",
            step_ord=step.ord,
            actor="resident",
            detail={"source": "agent"},
        )
        descriptor = await self._presentation.step_descriptor(session, routine, steps, step)
        return {
            "step_ord": descriptor["step_ord"],
            "prompt_text": descriptor["prompt_text"],
        }

    async def report_blocked(self, session_id: int, reason: str) -> dict:
        ctx = self._ctx
        session, _routine, _steps, step = ctx.load_runtime(session_id)
        ctx.store.add_event(
            session_id=session.id,
            at=ctx.now(),
            kind="step_blocked",
            step_ord=step.ord,
            actor="resident",
            detail={"reason": reason, "source": "agent"},
        )
        logger.info("guided_step_blocked", session_id=session.id, step_ord=step.ord)
        return {"acknowledged": True}

    async def request_help(self, session_id: int, reason: str | None = None) -> dict:
        ctx = self._ctx
        session, _routine, _steps, step = ctx.load_runtime(session_id)
        help_reason = reason or "resident_requested"
        ctx.store.update_session(
            session.id,
            status="escalated",
            last_activity_at=ctx.now(),
        )
        ctx.store.add_event(
            session_id=session.id,
            at=ctx.now(),
            kind="help_requested",
            step_ord=step.ord,
            actor="resident",
            detail={"reason": help_reason, "source": "agent"},
        )
        updated = ctx.store.get_session(session.id)
        if updated is None:
            raise NotFoundError("Guided session", session.id)
        await ctx.escalator.escalate(
            session=updated,
            reason=help_reason,
            emergency=False,
        )
        logger.info("guided_help_requested", session_id=session.id, step_ord=step.ord)
        return {"acknowledged": True}

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
