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
from backend.models.person import HouseholdMember
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
        person_location_service: Any = None,
        companion_surface_service: Any = None,
        ws_manager: Any = None,
        notification_dispatcher: Any = None,
        memory_query: Any = None,
        voice: SessionVoice | None = None,
        safety_watch: SafetyWatch | None = None,
        escalator: Escalator | None = None,
        settings: Settings | None = None,
        time_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._db_factory = db_factory
        self._scheduler = scheduler
        self._pipeline_executor = pipeline_executor
        self._person_location_service = person_location_service
        self._companion_surface_service = companion_surface_service
        self._ws_manager = ws_manager
        self._notification_dispatcher = notification_dispatcher
        self._memory_query = memory_query
        self._voice = voice or NoopSessionVoice()
        self._safety_watch = safety_watch or NoopSafetyWatch()
        self._escalator = escalator or NoopEscalator()
        self._settings = settings or default_settings
        self._time_fn = time_fn or (lambda: datetime.now(UTC))
        self._store = GuidedTaskStore(db_factory)

    def set_person_location_service(self, person_location_service: Any) -> None:
        self._person_location_service = person_location_service

    async def start(
        self,
        routine_id: int,
        person_id: str,
        *,
        execution_id: int | None = None,
        surface_id: str | None = None,
    ) -> GuidedSession:
        return await self.request_start(
            routine_id,
            person_id,
            execution_id=execution_id,
            surface_id=surface_id,
            require_presence=False,
        )

    async def request_start(
        self,
        routine_id: int,
        person_id: str,
        *,
        execution_id: int | None = None,
        surface_id: str | None = None,
        require_presence: bool = True,
        summon_timeout_s: int = 300,
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

        if not require_presence:
            session = self._store.create_session(
                routine_id=routine_id,
                person_id=person_id,
                status="active",
                execution_id=execution_id,
                surface_id=surface_id,
                now=now,
            )
            return await self._begin_session(session.id, routine=routine, steps=steps, now=now)

        location = await self._current_location(person_id)
        selected_surface_id = surface_id
        if selected_surface_id is None and location is not None and location.room_id is not None:
            surfaces = self._surfaces_in_room(location.room_id)
            if surfaces:
                selected_surface_id = surfaces[0].id

        if selected_surface_id is not None and self._has_live_realtime_session():
            session = self._store.create_session(
                routine_id=routine_id,
                person_id=person_id,
                status="active",
                execution_id=execution_id,
                surface_id=selected_surface_id,
                now=now,
            )
            return await self._begin_session(session.id, routine=routine, steps=steps, now=now)

        session = self._store.create_session(
            routine_id=routine_id,
            person_id=person_id,
            status="summoning",
            execution_id=execution_id,
            surface_id=selected_surface_id,
            now=now,
        )
        self._store.add_event(
            session_id=session.id,
            at=now,
            kind="summon_started",
            step_ord=None,
            actor="system",
            detail={"summon_timeout_s": summon_timeout_s},
        )
        await self._announce_summon(
            session=session,
            routine=routine,
            room_name=self._location_room_name(location),
            broad=selected_surface_id is None,
        )
        self._schedule_summon_recheck(session.id, summon_timeout_s, now)
        if selected_surface_id is not None:
            await self._cross_check_surface(selected_surface_id, person_id)
        return session

    async def on_session_opened(self) -> None:
        """Best-effort hook called when a realtime companion session opens.

        Invoked fire-and-forget from the websocket connect path, so it must never
        raise into the audio loop: a failure to re-check one summoning session is
        logged and the rest are still attempted.
        """
        for session in self._store.list_summoning_sessions():
            try:
                await self._summon_recheck(
                    session.id, self._settings.as_int("guided_task.step_timeout_s")
                )
            except Exception:
                logger.exception("guided_on_session_opened_recheck_failed", session_id=session.id)

    async def _begin_session(
        self,
        session_id: int,
        *,
        routine: Routine | None = None,
        steps: list[RoutineStep] | None = None,
        now: datetime | None = None,
    ) -> GuidedSession:
        begin_at = now or self._now()
        session = self._store.get_session(session_id)
        if session is None:
            raise NotFoundError("Guided session", session_id)
        if routine is None or steps is None:
            routine, steps = self._load_routine_and_steps(session.routine_id)
        updated = self._store.update_session(
            session_id,
            status="active",
            current_step_ord=0,
            attempts=0,
            last_activity_at=begin_at,
        )
        if updated is None:
            raise NotFoundError("Guided session", session_id)
        step = steps[0]
        self._store.add_event(
            session_id=session_id,
            at=begin_at,
            kind="step_entered",
            step_ord=step.ord,
            actor="system",
        )
        await self._speak(updated, step, is_retry=False)
        self._schedule_timeout(updated, routine, step, begin_at)
        return updated

    async def _summon_recheck(self, session_id: int, summon_timeout_s: int) -> None:
        now = self._now()
        session = self._store.get_session(session_id)
        if session is None or session.status != "summoning":
            return
        routine, steps = self._load_routine_and_steps(session.routine_id)
        if (now - session.started_at).total_seconds() > summon_timeout_s:
            updated = self._store.update_session(
                session.id,
                status="abandoned",
                completed_at=now,
                outcome="summon_timeout",
                last_activity_at=now,
            )
            self._store.add_event(
                session_id=session.id,
                at=now,
                kind="session_abandoned",
                step_ord=None,
                actor="system",
                detail={"outcome": "summon_timeout"},
            )
            logger.info("guided_summon_timeout", session_id=session.id, person_id=session.person_id)
            resume_owning_pipeline(
                self._pipeline_executor,
                self._db_factory,
                updated.execution_id if updated is not None else session.execution_id,
            )
            return

        location = await self._current_location(session.person_id)
        surface_id = session.surface_id
        if surface_id is None and location is not None and location.room_id is not None:
            surfaces = self._surfaces_in_room(location.room_id)
            if surfaces:
                surface_id = surfaces[0].id
                self._store.update_session(session.id, surface_id=surface_id, last_activity_at=now)

        if surface_id is not None and self._has_live_realtime_session():
            await self._begin_session(session.id, routine=routine, steps=steps, now=now)
            return

        if self._store.count_events(session_id=session.id, kind="summon_announced") <= 1:
            await self._announce_summon(
                session=session,
                routine=routine,
                room_name=self._location_room_name(location),
                broad=surface_id is None,
            )
        self._schedule_summon_recheck(session.id, summon_timeout_s, now)

    async def get_active_step(self, session_id: int) -> dict:
        session = self._store.get_session(session_id)
        if session is None:
            raise NotFoundError("Guided session", session_id)
        if session.status == "completed":
            return {"done": True}
        routine, steps = self._load_routine_steps(session.routine_id)
        if not steps:
            raise ValidationError("Routine has no steps")
        step = self._step_by_ord(steps, session.current_step_ord)
        return await self._step_descriptor(session, routine, steps, step)

    async def handle_completion(self, session_id: int, evidence: dict) -> dict:
        now = self._now()
        session, routine, steps, step = self._load_runtime(session_id)
        expected_step_ord = evidence.get("step_ord")
        if expected_step_ord is not None and expected_step_ord != session.current_step_ord:
            decision = Decision(
                kind="noop",
                next_status=session.status,
                next_step_ord=session.current_step_ord,
                attempts=session.attempts,
                reason="stale_step_completion",
            )
            return self._decision_descriptor(decision)

        evaluator = build_evaluators(step.completion_gate)[0]
        result = await evaluator.is_complete(session=session, step=step, evidence=evidence)
        if not result.complete:
            decision = Decision(
                kind="wait",
                next_status=session.status,
                next_step_ord=session.current_step_ord,
                attempts=session.attempts,
                reason=result.reason,
            )
            return self._decision_descriptor(decision)

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
            speak_on_advance=False,
        )
        return await self._advance_descriptor(session.id, routine, steps, decision)

    async def repeat_step(self, session_id: int) -> dict:
        session, routine, steps, step = self._load_runtime(session_id)
        self._store.add_event(
            session_id=session.id,
            at=self._now(),
            kind="step_repeated",
            step_ord=step.ord,
            actor="resident",
            detail={"source": "agent"},
        )
        descriptor = await self._step_descriptor(session, routine, steps, step)
        return {
            "step_ord": descriptor["step_ord"],
            "prompt_text": descriptor["prompt_text"],
        }

    async def report_blocked(self, session_id: int, reason: str) -> dict:
        session, _routine, _steps, step = self._load_runtime(session_id)
        self._store.add_event(
            session_id=session.id,
            at=self._now(),
            kind="step_blocked",
            step_ord=step.ord,
            actor="resident",
            detail={"reason": reason, "source": "agent"},
        )
        logger.info("guided_step_blocked", session_id=session.id, step_ord=step.ord)
        return {"acknowledged": True}

    async def request_help(self, session_id: int, reason: str | None = None) -> dict:
        session, _routine, _steps, step = self._load_runtime(session_id)
        help_reason = reason or "resident_requested"
        self._store.update_session(
            session.id,
            status="escalated",
            last_activity_at=self._now(),
        )
        self._store.add_event(
            session_id=session.id,
            at=self._now(),
            kind="help_requested",
            step_ord=step.ord,
            actor="resident",
            detail={"reason": help_reason, "source": "agent"},
        )
        updated = self._store.get_session(session.id)
        if updated is None:
            raise NotFoundError("Guided session", session.id)
        await self._escalator.escalate(
            session=updated,
            reason=help_reason,
            emergency=False,
        )
        logger.info("guided_help_requested", session_id=session.id, step_ord=step.ord)
        return {"acknowledged": True}

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
        speak_on_advance: bool = True,
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
            if speak_on_advance:
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
        routine = self._store.get_routine(session.routine_id)
        if routine is None:
            raise NotFoundError("Routine", session.routine_id)
        rendered = await self._render_step_prompt(session, routine, step)
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
            resident_name=self._resident_name(session.person_id),
        )
        await self._voice.speak_step(
            session=voice_session,
            step=step,
            rendered_prompt=rendered,
            is_retry=is_retry,
        )

    async def _step_descriptor(
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

    async def _advance_descriptor(
        self,
        session_id: int,
        routine: Routine,
        steps: list[RoutineStep],
        decision: Decision,
    ) -> dict:
        base = self._decision_descriptor(decision)
        if decision.kind == "complete":
            base.update({"advanced": True, "done": True, "next_step": None})
            return base
        if decision.kind not in {"advance", "skip"}:
            return base
        updated = self._store.get_session(session_id)
        if updated is None:
            raise NotFoundError("Guided session", session_id)
        next_step = self._step_by_ord(steps, decision.next_step_ord)
        base.update(
            {
                "advanced": True,
                "done": False,
                "next_step": await self._step_descriptor(updated, routine, steps, next_step),
            }
        )
        return base

    def _decision_descriptor(self, decision: Decision) -> dict:
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

    async def _render_step_prompt(
        self,
        session: GuidedSession,
        routine: Routine,
        step: RoutineStep,
    ) -> str:
        memory_context = await self._memory_context(session, routine)
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
            },
        )

    async def _memory_context(self, session: GuidedSession, routine: Routine) -> str:
        memory_query = self._memory_query
        if memory_query is None:
            return ""
        try:
            hits = await memory_query.search_observations(routine.name, limit=3)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "guided_memory_context_unavailable",
                session_id=session.id,
                error=str(exc),
            )
            return ""
        summaries: list[str] = []
        for hit in hits:
            description = getattr(hit, "description", "")
            if description:
                summaries.append(str(description))
        return " ".join(summaries[:3])

    def _resident_name(self, person_id: str) -> str:
        db = self._db_factory()
        try:
            member = db.get(HouseholdMember, person_id)
            if member is not None and member.name:
                return member.name
            return person_id
        finally:
            db.close()

    async def _current_location(self, person_id: str) -> Any | None:
        person_location = self._person_location_service
        if person_location is None:
            return None
        return await person_location.where_is(person_id)

    def _surfaces_in_room(self, room_id: int) -> list[Any]:
        companion_surfaces = self._companion_surface_service
        if companion_surfaces is None:
            return []
        return companion_surfaces.surfaces_in_room(room_id)

    def _has_live_realtime_session(self) -> bool:
        ws_manager = self._ws_manager
        if ws_manager is None:
            return False
        # TODO(multi-surface): route websocket presence by companion surface id.
        has_connections = ws_manager.has_connections
        if callable(has_connections):
            return bool(has_connections())
        return bool(has_connections)

    def _location_room_name(self, location: Any | None) -> str:
        if location is None:
            return "home"
        room_name = getattr(location, "room_name", None)
        if room_name:
            return str(room_name)
        room_id = getattr(location, "room_id", None)
        return f"room {room_id}" if room_id is not None else "home"

    async def _announce_summon(
        self,
        *,
        session: GuidedSession,
        routine: Routine,
        room_name: str,
        broad: bool,
    ) -> None:
        channels = routine.summon_channels_override or self._settings.as_list(
            "guided_task.summon_channels"
        )
        message = "Please come to the companion screen when you are ready for your routine."
        dispatcher = self._notification_dispatcher
        if dispatcher is None:
            logger.warning(
                "guided_summon_announce_skipped",
                session_id=session.id,
                reason="notification_dispatcher_unavailable",
            )
        else:
            try:
                await dispatcher.dispatch(
                    alert_level="reminder",
                    message=message,
                    room_name=room_name,
                    rule_config={"channels": channels},
                )
            except Exception:
                logger.exception("guided_summon_announce_failed", session_id=session.id)
        self._store.add_event(
            session_id=session.id,
            at=self._now(),
            kind="summon_announced",
            step_ord=None,
            actor="system",
            detail={"channels": channels, "room_name": room_name, "broad": broad},
        )
        logger.info(
            "guided_summon_announced",
            session_id=session.id,
            room_name=room_name,
            channels=channels,
            broad=broad,
        )

    async def _cross_check_surface(self, surface_id: str, person_id: str) -> None:
        companion_surfaces = self._companion_surface_service
        if companion_surfaces is None:
            return
        await companion_surfaces.cross_check_room(surface_id, person_id)

    def _schedule_summon_recheck(
        self,
        session_id: int,
        summon_timeout_s: int,
        now: datetime,
    ) -> None:
        interval_s = max(1, min(30, summon_timeout_s // 4))
        scheduler = self._scheduler
        if scheduler is not None and not hasattr(scheduler, "apscheduler"):
            scheduler = SimpleNamespace(apscheduler=scheduler)
        schedule_session_timeout(
            scheduler,
            job_id=f"guided_summon_recheck_{session_id}",
            run_at=now + timedelta(seconds=interval_s),
            finalize=self._summon_recheck,
            args=[session_id, summon_timeout_s],
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
