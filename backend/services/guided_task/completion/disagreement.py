"""Bounded vision/response disagreement resolution (G1/D24), split out of
``runtime.py`` to keep that module under the package's 500-line guard.

Leaf module: takes explicit parameters (the runtime context, session,
routine, steps) rather than depending on ``runtime.py``, so ``runtime.py``
can import this without creating a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.models.guided_task import GuidedSession as GuidedSessionModel
from backend.models.guided_task import Routine, RoutineStep
from backend.services.guided_task.context import RuntimeContext
from backend.services.guided_task.domain import Decision
from backend.services.guided_task.policy import resolve_policy, resolve_vision_override
from backend.services.guided_task.state_machine import GuidedTaskStateMachine


@dataclass
class DisagreementOutcome:
    """What ``handle_completion`` should do after a resident/vision disagreement."""

    decision: Decision
    apply: bool
    advance: bool
    event_kind: str = ""
    detail: dict | None = None


async def resolve_vision_disagreement(
    *,
    ctx: RuntimeContext,
    session: GuidedSessionModel,
    routine: Routine,
    step: RoutineStep,
    steps: list[RoutineStep],
    vision_detail: dict[str, Any],
    evidence: dict[str, Any],
    result_reason: str,
    now: datetime,
) -> DisagreementOutcome:
    """Resolve the bounded-disagreement escape hatch (D24) for one "not done" tick.

    Called only when the resident asserted "done" (``evidence["confirmed"]``)
    while the vision gate disagreed. Counts recorded ``vision_confirm``
    disagreement events for this step and either holds (``apply=False``,
    caller returns ``decision_descriptor`` without persisting anything new),
    escalates, or defers to her word and advances -- mirroring the
    pre-extraction inline logic in ``handle_completion`` exactly.
    """
    confirm_cfg = (step.completion_gate or {}).get("vision", {}).get("confirm") or {}
    routine_confirm_cfg = (getattr(routine, "config_json", None) or {}).get(
        "guided_task", {}
    ).get("vision", {}).get("confirm") or {}
    max_disagreements = resolve_vision_override(
        "max_disagreements",
        step_cfg=confirm_cfg,
        routine_cfg=routine_confirm_cfg,
        settings=ctx.settings,
        settings_path="guided_task.vision.confirm.max_disagreements",
        cast=int,
        default=2,
    )
    on_max = resolve_vision_override(
        "on_max_disagreements",
        step_cfg=confirm_cfg,
        routine_cfg=routine_confirm_cfg,
        settings=ctx.settings,
        settings_path="guided_task.vision.confirm.on_max_disagreements",
        cast=str,
        default="advance",
    )

    # Count disagreements in the DB for this step_ord.
    # Since the current one was just recorded, we fetch all of them.
    from sqlalchemy import select

    from backend.models.guided_task import GuidedSessionEvent

    db = ctx.db_factory()
    try:
        stmt = select(GuidedSessionEvent).where(
            GuidedSessionEvent.session_id == session.id,
            GuidedSessionEvent.step_ord == step.ord,
            GuidedSessionEvent.kind == "vision_confirm",
        )
        events = db.execute(stmt).scalars().all()
        total_disagreements = sum(
            1 for e in events if e.detail and e.detail.get("complete") is False
        )
    finally:
        db.close()

    if total_disagreements < max_disagreements:
        decision = Decision(
            kind="wait",
            next_status=session.status,
            next_step_ord=session.current_step_ord,
            attempts=session.attempts,
            reason=vision_detail.get("reason") or result_reason,
        )
        return DisagreementOutcome(decision=decision, apply=False, advance=False)

    # Bounded disagreement threshold reached: defer to her word or escalate
    if on_max == "escalate":
        decision = Decision(
            kind="escalate",
            next_status="escalated",
            next_step_ord=session.current_step_ord,
            attempts=session.attempts,
            reason="vision_disagreement_escalation",
            emergency=False,
        )
        return DisagreementOutcome(
            decision=decision,
            apply=True,
            advance=False,
            event_kind="vision_deferred",
            detail={
                "completion_reason": "vision_deferred_to_response",
                "disagreements": total_disagreements,
                "last_vision_reason": vision_detail.get("reason"),
                "action": "escalate",
            },
        )

    decision = GuidedTaskStateMachine.decide(
        ctx.session_view(session, steps),
        ctx.step_view(step),
        "step_completed",
        resolve_policy(routine, step, ctx.settings),
        now,
        evidence=evidence,
    )
    return DisagreementOutcome(
        decision=decision,
        apply=True,
        advance=True,
        event_kind="vision_deferred",
        detail={
            "completion_reason": "vision_deferred_to_response",
            "disagreements": total_disagreements,
            "last_vision_reason": vision_detail.get("reason"),
            "action": "advance",
        },
    )
