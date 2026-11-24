"""The guided session's lease on the companion surface in the resident's room.

Leaf module: depends only on ``RuntimeContext`` and the pure ``policy`` module.
``Presentation`` calls it on every transition and at the end of a session; the
lease owner is the session's voice owner key, so a quiz or card running on the
same surface holds its own lease and never closes this one (or the reverse).
"""

from __future__ import annotations

from backend.models.guided_task import GuidedSession, Routine, RoutineStep
from backend.services.companion_surface.hardware import (
    capture_lease_seconds,
    engage_surface,
    release_surface,
)
from backend.services.guided_task.agent_voice import GUIDED_TASK_DELIVERY_TYPE
from backend.services.guided_task.context import RuntimeContext
from backend.services.guided_task.policy import resolve_policy
from backend.services.interactive_session.tagging import voice_owner_key


def lease_owner(session_id: int) -> str:
    """The lease owner for a guided session (its voice owner key)."""
    return voice_owner_key(GUIDED_TASK_DELIVERY_TYPE, session_id)


def step_lease_seconds(ctx: RuntimeContext, routine: Routine, step: RoutineStep) -> int:
    """A lease that outlives the step's own timeout, so a retry finds the microphone open."""
    return capture_lease_seconds(
        resolve_policy(routine, step, ctx.settings).step_timeout_s, settings=ctx.settings
    )


async def renew(ctx: RuntimeContext, session: GuidedSession) -> None:
    """Keep her room's microphone open for the step now on screen.

    Called on every transition with a step in progress, because a step the agent
    advanced to is not spoken again: without the renewal the previous step's lease
    would close the microphone partway through this one.
    """
    routine, steps = ctx.load_routine_steps(session.routine_id)
    if not steps:
        return
    step = ctx.step_by_ord(steps, session.current_step_ord)
    await engage_surface(
        ctx.ws_manager,
        session.surface_id,
        owner=lease_owner(session.id),
        reason=GUIDED_TASK_DELIVERY_TYPE,
        lease_seconds=step_lease_seconds(ctx, routine, step),
        settings=ctx.settings,
    )


async def release(ctx: RuntimeContext, session_id: int) -> None:
    """End the session's lease; other deliveries' leases on the surface are untouched."""
    session = ctx.store.get_session(session_id)
    if session is None:
        return
    await release_surface(
        ctx.ws_manager,
        session.surface_id,
        owner=lease_owner(session_id),
        reason=GUIDED_TASK_DELIVERY_TYPE,
    )
