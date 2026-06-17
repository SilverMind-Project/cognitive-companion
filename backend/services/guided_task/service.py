"""Guided-task lifecycle service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.core.config import settings as default_settings
from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.core.template import render_template
from backend.models.guided_task import GuidedSession, Routine, RoutineStep
from backend.services.guided_task.completion.response import build_evaluators
from backend.services.guided_task.domain import Decision, SessionView, StepView
from backend.services.guided_task.policy import resolve_policy
from backend.services.guided_task.ports import (
    Escalator,
    NoopEscalator,
    NoopSafetyWatch,
    NoopSessionVoice,
    SafetyWatch,
    SessionVoice,
)
from backend.services.guided_task.state_machine import GuidedTaskStateMachine
from backend.services.guided_task.store import GuidedTaskStore
from backend.services.interactive_session.pipeline_link import (
    resume_owning_pipeline,
    schedule_session_timeout,
)

logger = get_logger(__name__)


class GuidedTaskService:
    """Headless guided-task runtime for routines, sessions, and events."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        scheduler: Any = None,
        pipeline_executor: Any = None,
        voice: SessionVoice | None = None,
        safety_watch: SafetyWatch | None = None,
        escalator: Escalator | None = None,
        settings: Settings | None = None,
        time_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._db_factory = db_factory
        self._scheduler = scheduler
        self._pipeline_executor = pipeline_executor
        self._voice = voice or NoopSessionVoice()
        self._safety_watch = safety_watch or NoopSafetyWatch()
        self._escalator = escalator or NoopEscalator()
        self._settings = settings or default_settings
        self._time_fn = time_fn or (lambda: datetime.now(UTC))
        self._store = GuidedTaskStore(db_factory)

    async def start(
        self,
        routine_id: int,
        person_id: str,
        *,
        execution_id: int | None = None,
        surface_id: str | None = None,
    ) -> GuidedSession:
        now = self._now()
        routine, steps = self._load_routine_and_steps(routine_id)
        if routine.person_id != person_id:
            logger.warning(
                "guided_start_person_mismatch",
                routine_id=routine_id,
                routine_person_id=routine.person_id,
                person_id=person_id,
            )
            raise ValidationError("Routine does not belong to the requested person")
        live = self._store.get_live_session_for_person(person_id)
        if live is not None:
            logger.warning("guided_live_session_exists", person_id=person_id, session_id=live.id)
            raise ConflictError(f"Live guided session already exists for person '{person_id}'")

        session = self._store.create_session(
            routine_id=routine_id,
            person_id=person_id,
            status="active",
            execution_id=execution_id,
            surface_id=surface_id,
            now=now,
        )
        step = steps[0]
        self._store.add_event(
            session_id=session.id,
            at=now,
            kind="step_entered",
            step_ord=step.ord,
            actor="system",
        )
        await self._speak(session, step, is_retry=False)
        self._schedule_timeout(session, routine, step, now)
        return session

    async def handle_completion(self, session_id: int, evidence: dict) -> Decision:
        now = self._now()
        session, routine, steps, step = self._load_runtime(session_id)
        expected_step_ord = evidence.get("step_ord")
        if expected_step_ord is not None and expected_step_ord != session.current_step_ord:
            return Decision(
                kind="noop",
                next_status=session.status,
                next_step_ord=session.current_step_ord,
                attempts=session.attempts,
                reason="stale_step_completion",
            )

        evaluator = build_evaluators(step.completion_gate)[0]
        result = await evaluator.is_complete(session=session, step=step, evidence=evidence)
        if not result.complete:
            return Decision(
                kind="wait",
                next_status=session.status,
                next_step_ord=session.current_step_ord,
                attempts=session.attempts,
                reason=result.reason,
            )

        decision = GuidedTaskStateMachine.decide(
            self._session_view(session, steps),
            self._step_view(step),
            "step_completed",
            resolve_policy(routine, step, self._settings),
            now,
            evidence=evidence,
        )
        await self._apply_decision(
            session=session,
            routine=routine,
            steps=steps,
            decision=decision,
            now=now,
            event_kind="step_completed",
            actor="resident",
            detail={"completion_reason": result.reason},
        )
        return decision

    async def on_step_timeout(self, session_id: int) -> Decision:
        now = self._now()
        session, routine, steps, step = self._load_runtime(session_id)
        decision = GuidedTaskStateMachine.decide(
            self._session_view(session, steps),
            self._step_view(step),
            "timeout_tick",
            resolve_policy(routine, step, self._settings),
            now,
        )
        await self._apply_decision(
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

    async def resume(self, session_id: int) -> Decision:
        now = self._now()
        session, routine, steps, step = self._load_runtime(session_id)
        decision = GuidedTaskStateMachine.decide(
            self._session_view(session, steps),
            self._step_view(step),
            "resume",
            resolve_policy(routine, step, self._settings),
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

    async def tick(self, now: datetime | None = None) -> None:
        tick_at = now or self._now()
        for session in self._store.list_live_sessions():
            routine, steps = self._load_routine_steps(session.routine_id)
            step = self._step_by_ord(steps, session.current_step_ord)
            policy = resolve_policy(routine, step, self._settings)
            if (tick_at - session.last_activity_at).total_seconds() > policy.resume_grace_s:
                decision = GuidedTaskStateMachine.decide(
                    self._session_view(session, steps),
                    self._step_view(step),
                    "resume",
                    policy,
                    tick_at,
                )
                await self._apply_decision(
                    session=session,
                    routine=routine,
                    steps=steps,
                    decision=decision,
                    now=tick_at,
                    event_kind="session_abandoned",
                    actor="system",
                    detail={"reason": decision.reason},
                )
                continue

            for safety_event in await self._safety_watch.evaluate(session=session):
                decision = GuidedTaskStateMachine.decide(
                    self._session_view(session, steps),
                    self._step_view(step),
                    "safety_event",
                    policy,
                    tick_at,
                    evidence=safety_event,
                )
                await self._apply_decision(
                    session=session,
                    routine=routine,
                    steps=steps,
                    decision=decision,
                    now=tick_at,
                    event_kind="safety_event",
                    actor="system",
                    detail=safety_event,
                )

    async def complete(self, session_id: int, outcome: str) -> GuidedSession:
        now = self._now()
        session = self._store.get_session(session_id)
        if session is None:
            raise NotFoundError("Guided session", session_id)
        updated = self._store.update_session(
            session_id,
            status="completed",
            completed_at=now,
            outcome=outcome,
            last_activity_at=now,
        )
        if updated is None:
            raise NotFoundError("Guided session", session_id)
        self._store.add_event(
            session_id=session_id,
            at=now,
            kind="session_completed",
            step_ord=session.current_step_ord,
            actor="system",
            detail={"outcome": outcome},
        )
        resume_owning_pipeline(self._pipeline_executor, self._db_factory, updated.execution_id)
        return updated

    def _now(self) -> datetime:
        now = self._time_fn()
        if now.tzinfo is None:
            raise ValueError("GuidedTaskService time_fn must return timezone-aware datetimes")
        return now

    def _load_routine_and_steps(self, routine_id: int) -> tuple[Routine, list[RoutineStep]]:
        routine, steps = self._load_routine_steps(routine_id)
        if not routine.is_enabled:
            raise ValidationError("Routine is disabled")
        if not steps:
            raise ValidationError("Routine has no steps")
        return routine, steps

    def _load_routine_steps(self, routine_id: int) -> tuple[Routine, list[RoutineStep]]:
        routine = self._store.get_routine(routine_id)
        if routine is None:
            raise NotFoundError("Routine", routine_id)
        steps = self._store.list_steps(routine_id)
        return routine, steps

    def _load_runtime(
        self, session_id: int
    ) -> tuple[GuidedSession, Routine, list[RoutineStep], RoutineStep]:
        session = self._store.get_session(session_id)
        if session is None:
            raise NotFoundError("Guided session", session_id)
        routine, steps = self._load_routine_steps(session.routine_id)
        if not steps:
            raise ValidationError("Routine has no steps")
        return session, routine, steps, self._step_by_ord(steps, session.current_step_ord)

    def _step_by_ord(self, steps: list[RoutineStep], step_ord: int) -> RoutineStep:
        for step in steps:
            if step.ord == step_ord:
                return step
        raise ValidationError(f"Routine step {step_ord} is missing")

    def _session_view(self, session: GuidedSession, steps: list[RoutineStep]) -> SessionView:
        step_entered_at = self._store.latest_event_at(
            session_id=session.id,
            kind="step_entered",
            step_ord=session.current_step_ord,
        )
        return SessionView(
            status=session.status,
            current_step_ord=session.current_step_ord,
            attempts=session.attempts,
            num_steps=len(steps),
            started_at=session.started_at,
            last_activity_at=session.last_activity_at,
            step_entered_at=step_entered_at or session.started_at,
        )

    def _step_view(self, step: RoutineStep) -> StepView:
        return StepView(
            ord=step.ord,
            has_skip_condition=step.skip_condition is not None,
            min_duration_s=step.min_duration_s,
            is_safety_critical=step.is_safety_critical,
        )

    async def _apply_decision(
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
    ) -> None:
        if decision.kind == "noop":
            return

        current_step = self._step_by_ord(steps, session.current_step_ord)
        if decision.kind == "wait":
            self._store.add_event(
                session_id=session.id,
                at=now,
                kind=event_kind,
                step_ord=current_step.ord,
                actor=actor,
                detail=detail,
            )
            return

        self._store.add_event(
            session_id=session.id,
            at=now,
            kind=event_kind,
            step_ord=current_step.ord,
            actor=actor,
            detail=detail,
        )

        if decision.kind in {"advance", "skip"}:
            if decision.kind == "skip":
                self._store.add_event(
                    session_id=session.id,
                    at=now,
                    kind="step_skipped",
                    step_ord=current_step.ord,
                    actor="system",
                    detail={"reason": decision.reason},
                )
            updated = self._store.update_session(
                session.id,
                status=decision.next_status,
                current_step_ord=decision.next_step_ord,
                attempts=decision.attempts,
                last_activity_at=now,
            )
            if updated is None:
                raise NotFoundError("Guided session", session.id)
            next_step = self._step_by_ord(steps, decision.next_step_ord)
            self._store.add_event(
                session_id=session.id,
                at=now,
                kind="step_entered",
                step_ord=next_step.ord,
                actor="system",
            )
            await self._speak(updated, next_step, is_retry=False)
            self._schedule_timeout(updated, routine, next_step, now)
            return

        if decision.kind == "retry":
            updated = self._store.update_session(
                session.id,
                status=decision.next_status,
                attempts=decision.attempts,
                last_activity_at=now,
            )
            if updated is None:
                raise NotFoundError("Guided session", session.id)
            if event_kind != "retry":
                self._store.add_event(
                    session_id=session.id,
                    at=now,
                    kind="retry",
                    step_ord=current_step.ord,
                    actor="system",
                    detail={"reason": decision.reason},
                )
            await self._speak(updated, current_step, is_retry=True)
            self._schedule_timeout(updated, routine, current_step, now)
            return

        if decision.kind == "escalate":
            updated = self._store.update_session(
                session.id,
                status=decision.next_status,
                attempts=decision.attempts,
                last_activity_at=now,
            )
            if updated is None:
                raise NotFoundError("Guided session", session.id)
            self._store.add_event(
                session_id=session.id,
                at=now,
                kind="escalation",
                step_ord=current_step.ord,
                actor="system",
                detail={"reason": decision.reason, "emergency": decision.emergency},
            )
            await self._escalator.escalate(
                session=updated,
                reason=decision.reason,
                emergency=decision.emergency,
            )
            return

        if decision.kind == "takeover":
            self._store.update_session(
                session.id,
                status=decision.next_status,
                last_activity_at=now,
            )
            self._store.add_event(
                session_id=session.id,
                at=now,
                kind="takeover_started",
                step_ord=current_step.ord,
                actor="caregiver",
                detail={"reason": decision.reason},
            )
            return

        if decision.kind == "abandon":
            self._store.update_session(
                session.id,
                status=decision.next_status,
                completed_at=now,
                outcome="abandoned",
                last_activity_at=now,
            )
            return

        if decision.kind == "complete":
            await self.complete(session.id, "completed")

    async def _speak(self, session: GuidedSession, step: RoutineStep, *, is_retry: bool) -> None:
        rendered = render_template(
            step.prompt_template,
            {
                "session": {
                    "id": session.id,
                    "person_id": session.person_id,
                    "current_step_ord": session.current_step_ord,
                },
                "step": {"ord": step.ord},
            },
        )
        await self._voice.speak_step(
            session=session,
            step=step,
            rendered_prompt=rendered,
            is_retry=is_retry,
        )

    def _schedule_timeout(
        self,
        session: GuidedSession,
        routine: Routine,
        step: RoutineStep,
        now: datetime,
    ) -> None:
        policy = resolve_policy(routine, step, self._settings)
        scheduler = self._scheduler
        if scheduler is not None and not hasattr(scheduler, "apscheduler"):
            scheduler = SimpleNamespace(apscheduler=scheduler)
        schedule_session_timeout(
            scheduler,
            job_id=f"guided_session_timeout_{session.id}",
            run_at=now + timedelta(seconds=policy.step_timeout_s),
            finalize=self.on_step_timeout,
            args=[session.id],
        )
