"""Shared runtime plumbing for the guided-task package (M29).

``RuntimeContext`` is the single object every collaborator module in this
package is constructed with. It owns the dependencies that used to live as
``self._x`` attributes on the monolithic ``GuidedTaskService`` plus the small
cross-cutting helpers that more than one collaborator needs (session/step
loading, the state-machine view builders, terminal-transition bookkeeping).
It is held by reference, never copied: bootstrap setters
(``set_zone_service`` and friends) mutate fields on this one instance after
construction, so every collaborator must read fields off ``ctx`` at call
time rather than snapshotting them into its own attributes.

Helpers used by exactly one collaborator module stay defined on that module
instead of here (``_schedule_summon_recheck``, ``_current_location``, and
similar single-caller helpers live in ``summon.py``; ``_escalation_grace_s``
lives in ``watch.py``; ``_record_vision_confirm_event`` lives in
``runtime.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from cachetools import TTLCache
from sqlalchemy.orm import Session

from backend.core.config import SettingNotFoundError, Settings
from backend.core.config import settings as default_settings
from backend.core.exceptions import NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.models.guided_task import GuidedSession, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.observability.metrics import location_metrics as guided_metrics
from backend.services.guided_task.domain import SessionView, StepView
from backend.services.guided_task.ports import (
    Escalator,
    NoopEscalator,
    NoopSafetyWatch,
    NoopSessionVoice,
    SafetyWatch,
    SessionVoice,
)
from backend.services.guided_task.store import GuidedTaskStore
from backend.services.interactive_session.pipeline_link import resume_owning_pipeline
from backend.services.knowledge.voice_instructions import VoiceInstructionConfig

logger = get_logger(__name__)


class RuntimeContext:
    """Constructor-injected dependency bag plus cross-cutting helpers."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        scheduler: Any = None,
        pipeline_executor: Any = None,
        person_location_service: Any = None,
        zone_service: Any = None,
        bucketizer: Any = None,
        camera_topology: Any = None,
        llm_model_registry: Any = None,
        minio_client: Any = None,
        activity_service: Any = None,
        signals_service: Any = None,
        scene_analysis_client: Any = None,
        companion_surface_service: Any = None,
        ws_manager: Any = None,
        admin_ws_broadcaster: Any = None,
        notification_dispatcher: Any = None,
        conversation_manager: Any = None,
        memory_query: Any = None,
        scene_intel: Any = None,
        embedding_client: Any = None,
        knowledge_ingestion: Any = None,
        voice: SessionVoice | None = None,
        voice_instructions: VoiceInstructionConfig | None = None,
        safety_watch: SafetyWatch | None = None,
        escalator: Escalator | None = None,
        settings: Settings | None = None,
        time_fn: Callable[[], datetime] | None = None,
        gate_runner: Any = None,
        camera_source_resolver: Any = None,
        event_aggregator: Any = None,
    ) -> None:
        self.db_factory = db_factory
        self.scheduler = scheduler
        self.pipeline_executor = pipeline_executor
        self.person_location_service = person_location_service
        self.zone_service = zone_service
        self.bucketizer = bucketizer
        self.camera_topology = camera_topology
        self.llm_model_registry = llm_model_registry
        self.minio_client = minio_client
        self.activity_service = activity_service
        self.signals_service = signals_service
        self.scene_analysis_client = scene_analysis_client
        self.companion_surface_service = companion_surface_service
        self.ws_manager = ws_manager
        self.admin_ws_broadcaster = admin_ws_broadcaster
        self.notification_dispatcher = notification_dispatcher
        self.conversation_manager = conversation_manager
        self.memory_query = memory_query
        self.scene_intel = scene_intel
        self.embedding_client = embedding_client
        self.knowledge_ingestion = knowledge_ingestion
        self.voice = voice or NoopSessionVoice()
        self.voice_instructions = voice_instructions or VoiceInstructionConfig()
        self.safety_watch = safety_watch or NoopSafetyWatch()
        self.escalator = escalator or NoopEscalator()
        self.settings = settings or default_settings
        self.time_fn = time_fn or (lambda: datetime.now(UTC))
        self.store = GuidedTaskStore(db_factory)
        self.gate_runner = gate_runner
        self.camera_source_resolver = camera_source_resolver
        self.event_aggregator = event_aggregator
        try:
            resume_grace_s = self.settings.as_int("guided_task.resume_grace_s")
        except SettingNotFoundError:
            resume_grace_s = 600
        # TTL is a memory bound only; correctness relies on the
        # explicit elapsed-time comparisons at each read site, not on cache
        # eviction. Eagerly evicted per-session on terminal transitions too
        # (see evict_runtime_state).
        self.last_watch_at: TTLCache[tuple[int, int], datetime] = TTLCache(
            maxsize=4096, ttl=resume_grace_s, timer=lambda: self.time_fn().timestamp()
        )
        self.progress_seen_at: TTLCache[tuple[int, int], datetime] = TTLCache(
            maxsize=4096, ttl=resume_grace_s, timer=lambda: self.time_fn().timestamp()
        )

    # ------------------------------------------------------------------
    # Time and session/step loading
    # ------------------------------------------------------------------

    def now(self) -> datetime:
        now = self.time_fn()
        if now.tzinfo is None:
            raise ValueError("GuidedTaskService time_fn must return timezone-aware datetimes")
        return now

    def require_session(self, session_id: int) -> GuidedSession:
        session = self.store.get_session(session_id)
        if session is None:
            raise NotFoundError("Guided session", session_id)
        return session

    def load_routine_and_steps(self, routine_id: int) -> tuple[Routine, list[RoutineStep]]:
        routine, steps = self.load_routine_steps(routine_id)
        if not routine.is_enabled:
            raise ValidationError("Routine is disabled")
        if not steps:
            raise ValidationError("Routine has no steps")
        return routine, steps

    def load_routine_steps(self, routine_id: int) -> tuple[Routine, list[RoutineStep]]:
        routine = self.store.get_routine(routine_id)
        if routine is None:
            raise NotFoundError("Routine", routine_id)
        steps = self.store.list_steps(routine_id)
        return routine, steps

    def load_runtime(
        self, session_id: int
    ) -> tuple[GuidedSession, Routine, list[RoutineStep], RoutineStep]:
        session = self.store.get_session(session_id)
        if session is None:
            raise NotFoundError("Guided session", session_id)
        routine, steps = self.load_routine_steps(session.routine_id)
        if not steps:
            raise ValidationError("Routine has no steps")
        return session, routine, steps, self.step_by_ord(steps, session.current_step_ord)

    def step_by_ord(self, steps: list[RoutineStep], step_ord: int) -> RoutineStep:
        for step in steps:
            if step.ord == step_ord:
                return step
        raise ValidationError(f"Routine step {step_ord} is missing")

    def session_view(self, session: GuidedSession, steps: list[RoutineStep]) -> SessionView:
        step_entered_at = self.store.latest_event_at(
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

    def step_view(self, step: RoutineStep) -> StepView:
        return StepView(
            ord=step.ord,
            has_skip_condition=step.skip_condition is not None,
            min_duration_s=step.min_duration_s,
            is_safety_critical=step.is_safety_critical,
        )

    # ------------------------------------------------------------------
    # Terminal-transition bookkeeping (shared by summon/watch/runtime)
    # ------------------------------------------------------------------

    def mark_abandoned(self, session_id: int, *, now: datetime, outcome: str) -> GuidedSession:
        """Single write path for ``status='abandoned'`` (terminal-transition seam).

        Every abandon route (attempts/resume-grace via ``_apply_decision``,
        summon timeout, unanswered escalation) funnels through here so
        runtime caches are evicted exactly once, the owning pipeline resumes
        exactly once (mirroring ``complete()``; the M25/G6 park ceiling is a
        backstop for a wedged session, not the normal path for a clean
        abandon), and so a future terminal-transition hook (the Daily Living
        guided-memory bridge) has one place to attach rather than three.
        """
        updated = self.store.update_session(
            session_id,
            status="abandoned",
            completed_at=now,
            outcome=outcome,
            last_activity_at=now,
        )
        if updated is None:
            raise NotFoundError("Guided session", session_id)
        resume_owning_pipeline(self.pipeline_executor, self.db_factory, updated.execution_id)
        self.evict_runtime_state(session_id)
        guided_metrics.guided_sessions_total.labels(outcome=outcome).inc()
        return updated

    def evict_runtime_state(self, session_id: int) -> None:
        """Drop a terminated session's keys from all three runtime caches (G10).

        Cheap and avoids stale nag-suppression/cool-off reuse if a session id
        is ever reused across a restart-free process lifetime.
        """
        for cache in (self.last_watch_at, self.progress_seen_at):
            stale_keys = [key for key in list(cache.keys()) if key[0] == session_id]
            for key in stale_keys:
                cache.pop(key, None)
        gate_cache = getattr(self.gate_runner, "cache", None) if self.gate_runner else None
        if gate_cache is not None:
            gate_cache.evict_session(str(session_id))

    def link_conversation(
        self,
        session: GuidedSession,
        conversation_session_id: int,
        *,
        now: datetime,
        actor: str,
    ) -> GuidedSession:
        """Attach a conversation_sessions row to a guided session (M24, G2).

        Never key conversation reads or writes by a guided session id; this is
        the only place a guided session acquires its conversation linkage.
        """
        updated = self.store.update_session(
            session.id, conversation_session_id=conversation_session_id
        )
        if updated is None:
            raise NotFoundError("Guided session", session.id)
        self.store.add_event(
            session_id=session.id,
            at=now,
            kind="conversation_linked",
            step_ord=session.current_step_ord,
            actor=actor,
            detail={"conversation_session_id": conversation_session_id},
        )
        return updated

    def schedule_timeout(
        self,
        session: GuidedSession,
        routine: Routine,
        step: RoutineStep,
        now: datetime,
        *,
        finalize: Callable[[int], Any],
    ) -> None:
        from types import SimpleNamespace

        from backend.services.guided_task.policy import resolve_policy
        from backend.services.interactive_session.pipeline_link import schedule_session_timeout

        policy = resolve_policy(routine, step, self.settings)
        scheduler = self.scheduler
        if scheduler is not None and not hasattr(scheduler, "apscheduler"):
            scheduler = SimpleNamespace(apscheduler=scheduler)
        schedule_session_timeout(
            scheduler,
            job_id=f"guided_session_timeout_{session.id}",
            run_at=now + timedelta(seconds=policy.step_timeout_s),
            finalize=finalize,
            args=[session.id],
        )

    # ------------------------------------------------------------------
    # Misc cross-cutting helpers (2+ collaborator modules)
    # ------------------------------------------------------------------

    def resident_name(self, person_id: str) -> str:
        db = self.db_factory()
        try:
            member = db.get(HouseholdMember, person_id)
            if member is not None and member.name:
                return member.name
            return person_id
        finally:
            db.close()

    def identity_ids_for_person(self, person_id: str) -> set[str]:
        # CTS uses committed identity_id values as HouseholdMember.id values.
        # If a future deployment adds aliases, this resolver is the seam to
        # return all aliases without changing the camera cascade.
        return {person_id}

    def record_vision_confirm_event(
        self,
        session_id: int,
        step_ord: int | None,
        detail: dict[str, Any],
    ) -> None:
        self.store.add_event(
            session_id=session_id,
            at=self.now(),
            kind="vision_confirm",
            step_ord=step_ord,
            actor="system",
            detail=detail,
        )
        guided_metrics.guided_vision_calls_total.inc()
        if bool(detail.get("uncertain")):
            guided_metrics.guided_vision_uncertain_total.inc()
