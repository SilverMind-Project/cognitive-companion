"""Session runtime around the pure state machine (M29).

Depends on ``presentation.py`` (rendering/voice/broadcast) and
``retention.py`` (episodic write on completion), both leaf modules; never
imported by them (no cycle). ``summon.py``, ``watch.py``, and
``caregiver.py`` depend on this module's public methods
(``apply_decision``, ``maybe_skip_step``, ``complete``).
"""

from __future__ import annotations

from datetime import datetime

from backend.core.exceptions import NotFoundError
from backend.core.logging import get_logger
from backend.models.guided_task import GuidedSession, Routine, RoutineStep
from backend.observability.metrics import location_metrics as guided_metrics
from backend.services.guided_task.completion.activity import build_skip_evaluator
from backend.services.guided_task.completion.disagreement import resolve_vision_disagreement
from backend.services.guided_task.completion.response import build_evaluators, evaluate_completion
from backend.services.guided_task.context import RuntimeContext
from backend.services.guided_task.domain import Decision
from backend.services.guided_task.policy import resolve_policy
from backend.services.guided_task.presentation import Presentation
from backend.services.guided_task.retention import Retention
from backend.services.guided_task.state_machine import GuidedTaskStateMachine
from backend.services.interactive_session.pipeline_link import resume_owning_pipeline

logger = get_logger(__name__)


class Runtime:
    """Completion evaluation, decision application, and terminal transitions."""

    def __init__(
        self,
        ctx: RuntimeContext,
        presentation: Presentation,
        retention: Retention,
    ) -> None:
        self._ctx = ctx
        self._presentation = presentation
        self._retention = retention

    async def handle_completion(self, session_id: int, evidence: dict) -> dict:
        ctx = self._ctx
        now = ctx.now()
        session, routine, steps, step = ctx.load_runtime(session_id)
        expected_step_ord = evidence.get("step_ord")
        if expected_step_ord is not None and expected_step_ord != session.current_step_ord:
            decision = Decision(
                kind="noop",
                next_status=session.status,
                next_step_ord=session.current_step_ord,
                attempts=session.attempts,
                reason="stale_step_completion",
            )
            return self._presentation.decision_descriptor(decision)

        if evidence.get("already_done") and (step.skip_condition or {}).get(
            "kind"
        ) == "response_says_done":
            decision = GuidedTaskStateMachine.decide(
                ctx.session_view(session, steps),
                ctx.step_view(step),
                "skip_condition_met",
                resolve_policy(routine, step, ctx.settings),
                now,
            )
            await self.apply_decision(
                session=session,
                routine=routine,
                steps=steps,
                decision=decision,
                now=now,
                event_kind="skip_condition_met",
                actor="resident",
                detail={"reason": "response_says_done", "source": "agent"},
                speak_on_advance=False,
            )
            return await self._presentation.advance_descriptor(session.id, routine, steps, decision)

        evidence_with_now = {**evidence, "now": now, "routine": routine}
        evaluators = build_evaluators(
            step.completion_gate,
            activity_service=ctx.activity_service,
            zone_service=ctx.zone_service,
            person_location=ctx.person_location_service,
            bucketizer=ctx.bucketizer,
            camera_topology=ctx.camera_topology,
            identity_resolver=ctx.identity_ids_for_person,
            gate_runner=ctx.gate_runner,
            camera_source_resolver=ctx.camera_source_resolver,
            event_aggregator=ctx.event_aggregator,
            settings=ctx.settings,
            event_recorder=ctx.record_vision_confirm_event,
        )
        mode = str((step.completion_gate or {}).get("mode", "any"))
        evaluation = await evaluate_completion(
            evaluators=evaluators,
            mode=mode,
            session=session,
            step=step,
            evidence=evidence_with_now,
        )
        result = evaluation.result
        if not result.complete:
            # Check if resident asserted done and vision disagreed
            vision_detail = next(
                (d for d in evaluation.details if d["kind"] == "vision_confirm"), None
            )
            if (
                evidence.get("confirmed") is True
                and vision_detail is not None
                and vision_detail.get("complete") is False
            ):
                outcome = await resolve_vision_disagreement(
                    ctx=ctx,
                    session=session,
                    routine=routine,
                    step=step,
                    steps=steps,
                    vision_detail=vision_detail,
                    evidence=evidence,
                    result_reason=result.reason,
                    now=now,
                )
                if outcome.apply:
                    await self.apply_decision(
                        session=session,
                        routine=routine,
                        steps=steps,
                        decision=outcome.decision,
                        now=now,
                        event_kind=outcome.event_kind,
                        actor="resident",
                        detail=outcome.detail,
                        speak_on_advance=False,
                    )
                if outcome.advance:
                    return await self._presentation.advance_descriptor(
                        session.id, routine, steps, outcome.decision
                    )
                return self._presentation.decision_descriptor(outcome.decision)

            decision = Decision(
                kind="wait",
                next_status=session.status,
                next_step_ord=session.current_step_ord,
                attempts=session.attempts,
                reason=result.reason,
            )
            return self._presentation.decision_descriptor(decision)

        decision = GuidedTaskStateMachine.decide(
            ctx.session_view(session, steps),
            ctx.step_view(step),
            "step_completed",
            resolve_policy(routine, step, ctx.settings),
            now,
            evidence=evidence,
        )
        await self.apply_decision(
            session=session,
            routine=routine,
            steps=steps,
            decision=decision,
            now=now,
            event_kind="step_completed",
            actor="resident",
            detail={"completion_reason": result.reason, "gates": evaluation.details},
            speak_on_advance=False,
        )
        return await self._presentation.advance_descriptor(session.id, routine, steps, decision)

    async def on_step_timeout(self, session_id: int) -> Decision:
        ctx = self._ctx
        now = ctx.now()
        session, routine, steps, step = ctx.load_runtime(session_id)
        if session.status == "caregiver_takeover":
            return Decision(
                kind="noop",
                next_status=session.status,
                next_step_ord=session.current_step_ord,
                attempts=session.attempts,
                reason="caregiver_takeover_paused",
            )

        # Nag suppression (Part B)
        progress_seen_at = ctx.progress_seen_at.get((session.id, step.ord))
        policy = resolve_policy(routine, step, ctx.settings)
        if progress_seen_at is not None:
            elapsed = (now - progress_seen_at).total_seconds()
            if elapsed < policy.step_timeout_s:
                logger.info(
                    "nag_suppressed",
                    session_id=session.id,
                    step_ord=step.ord,
                    progress_seen_at=progress_seen_at,
                )
                ctx.schedule_timeout(session, routine, step, progress_seen_at, finalize=self.on_step_timeout)
                return Decision(
                    kind="noop",
                    next_status=session.status,
                    next_step_ord=session.current_step_ord,
                    attempts=session.attempts,
                    reason="nag_suppressed",
                )

        decision = GuidedTaskStateMachine.decide(
            ctx.session_view(session, steps),
            ctx.step_view(step),
            "timeout_tick",
            policy,
            now,
        )
        await self.apply_decision(
            session=session,
            routine=routine,
            steps=steps,
            decision=decision,
            now=now,
            event_kind="timeout",
            actor="system",
            detail={"reason": decision.reason},
        )
        return decision

    async def complete(
        self,
        session_id: int,
        outcome: str,
        *,
        actor: str = "system",
    ) -> GuidedSession:
        ctx = self._ctx
        now = ctx.now()
        session = ctx.store.get_session(session_id)
        if session is None:
            raise NotFoundError("Guided session", session_id)
        updated = ctx.store.update_session(
            session_id,
            status="completed",
            completed_at=now,
            outcome=outcome,
            last_activity_at=now,
        )
        if updated is None:
            raise NotFoundError("Guided session", session_id)
        ctx.evict_runtime_state(session_id)
        ctx.store.add_event(
            session_id=session_id,
            at=now,
            kind="session_completed",
            step_ord=session.current_step_ord,
            actor=actor,
            detail={"outcome": outcome},
        )
        guided_metrics.guided_sessions_total.labels(outcome=outcome).inc()
        await self._retention.write_session_observation(updated)
        resume_owning_pipeline(ctx.pipeline_executor, ctx.db_factory, updated.execution_id)
        return updated

    async def apply_decision(
        self,
        *,
        session: GuidedSession,
        routine: Routine,
        steps: list[RoutineStep],
        decision: Decision,
        now: datetime,
        event_kind: str,
        actor: str,
        detail: dict | None,
        speak_on_advance: bool = True,
        speak_prefix: str | None = None,
    ) -> None:
        ctx = self._ctx
        if decision.kind == "noop":
            return

        current_step = ctx.step_by_ord(steps, session.current_step_ord)
        if decision.kind == "wait":
            ctx.store.add_event(
                session_id=session.id,
                at=now,
                kind=event_kind,
                step_ord=current_step.ord,
                actor=actor,
                detail=detail,
            )
            return

        if decision.kind == "takeover":
            guided_metrics.guided_takeovers_total.inc()
            ctx.store.update_session(
                session.id,
                status=decision.next_status,
                last_activity_at=now,
            )
            ctx.store.add_event(
                session_id=session.id,
                at=now,
                kind="takeover_started",
                step_ord=current_step.ord,
                actor="caregiver",
                detail={"reason": decision.reason},
            )
            return

        ctx.store.add_event(
            session_id=session.id,
            at=now,
            kind=event_kind,
            step_ord=current_step.ord,
            actor=actor,
            detail=detail,
        )

        if decision.kind in {"advance", "skip"}:
            step_result = "skipped" if decision.kind == "skip" else "completed"
            guided_metrics.guided_steps_total.labels(result=step_result).inc()
            if decision.kind == "skip":
                ctx.store.add_event(
                    session_id=session.id,
                    at=now,
                    kind="step_skipped",
                    step_ord=current_step.ord,
                    actor="system",
                    detail={"reason": decision.reason},
                )
            updated = ctx.store.update_session(
                session.id,
                status=decision.next_status,
                current_step_ord=decision.next_step_ord,
                attempts=decision.attempts,
                last_activity_at=now,
            )
            if updated is None:
                raise NotFoundError("Guided session", session.id)
            next_step = ctx.step_by_ord(steps, decision.next_step_ord)
            ctx.store.add_event(
                session_id=session.id,
                at=now,
                kind="step_entered",
                step_ord=next_step.ord,
                actor="system",
            )
            skipped_further = await self.maybe_skip_step(
                session=updated,
                routine=routine,
                steps=steps,
                step=next_step,
                now=now,
                speak_on_advance=speak_on_advance,
            )
            if not skipped_further:
                if speak_on_advance:
                    await self._presentation.speak(
                        updated, next_step, is_retry=False, prefix=speak_prefix
                    )
                ctx.schedule_timeout(updated, routine, next_step, now, finalize=self.on_step_timeout)
            return

        if decision.kind == "retry":
            guided_metrics.guided_steps_total.labels(result="retried").inc()
            updated = ctx.store.update_session(
                session.id,
                status=decision.next_status,
                attempts=decision.attempts,
                last_activity_at=now,
            )
            if updated is None:
                raise NotFoundError("Guided session", session.id)
            if event_kind != "retry":
                ctx.store.add_event(
                    session_id=session.id,
                    at=now,
                    kind="retry",
                    step_ord=current_step.ord,
                    actor="system",
                    detail={"reason": decision.reason},
                )
            await self._presentation.speak(updated, current_step, is_retry=True)
            ctx.schedule_timeout(updated, routine, current_step, now, finalize=self.on_step_timeout)
            return

        if decision.kind == "escalate":
            guided_metrics.guided_escalations_total.labels(
                kind="emergency" if decision.emergency else "high"
            ).inc()
            updated = ctx.store.update_session(
                session.id,
                status=decision.next_status,
                attempts=decision.attempts,
                last_activity_at=now,
            )
            if updated is None:
                raise NotFoundError("Guided session", session.id)
            await ctx.escalator.escalate(
                session=updated,
                reason=decision.reason,
                emergency=decision.emergency,
            )
            return

        if decision.kind == "abandon":
            ctx.mark_abandoned(session.id, now=now, outcome="abandoned")
            return

        if decision.kind == "complete":
            guided_metrics.guided_steps_total.labels(result="completed").inc()
            await self.complete(session.id, "completed")

    async def maybe_skip_step(
        self,
        *,
        session: GuidedSession,
        routine: Routine,
        steps: list[RoutineStep],
        step: RoutineStep,
        now: datetime,
        speak_on_advance: bool,
    ) -> bool:
        """Evaluate ``step``'s skip_condition on entry (D8, G4).

        Only ``activity_signal`` and ``zone_presence`` are evaluated here;
        ``response_says_done`` fires solely via the ``already_done`` evidence
        path in ``handle_completion``. When satisfied, dispatches
        ``skip_condition_met`` through :meth:`apply_decision`, which
        recurses back into this method for the newly-entered step -- bounded
        automatically because each skip strictly advances
        ``current_step_ord``. ``speak_on_advance`` is forwarded unchanged
        through the whole cascade, so the caller's original intent (speak the
        step actually landed on, or stay silent because the agent's own turn
        owns the announcement) survives any number of skips. Returns ``True``
        when the step was skipped (the caller must not speak or schedule a
        timeout for it itself; a landed, non-skipped step deeper in the
        cascade was already spoken/scheduled here if ``speak_on_advance`` was
        set), ``False`` otherwise.
        """
        ctx = self._ctx
        evaluator = build_skip_evaluator(
            step.skip_condition,
            activity_service=ctx.activity_service,
            zone_service=ctx.zone_service,
        )
        if evaluator is None:
            return False
        result = await evaluator.is_complete(session=session, step=step, evidence={"now": now})
        if not result.complete:
            return False
        decision = GuidedTaskStateMachine.decide(
            ctx.session_view(session, steps),
            ctx.step_view(step),
            "skip_condition_met",
            resolve_policy(routine, step, ctx.settings),
            now,
        )
        await self.apply_decision(
            session=session,
            routine=routine,
            steps=steps,
            decision=decision,
            now=now,
            event_kind="skip_condition_met",
            actor="system",
            detail={"reason": result.reason, "skip_kind": (step.skip_condition or {}).get("kind")},
            speak_on_advance=speak_on_advance,
        )
        return True
