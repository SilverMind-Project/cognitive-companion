"""Guided-task lifecycle service: façade over the guided_task package (M29).

``GuidedTaskService`` is the composition root and the only public entry
point routers, MCP tools, and ``main.py`` construct. It builds one shared
``RuntimeContext`` and each concern collaborator (routine admin,
presentation, retention, runtime, summon, watch, caregiver) in dependency
order, then delegates every public method to the collaborator that owns it.
Bootstrap setters (``set_zone_service`` and friends) write through to the
one shared context so already-constructed collaborators see the update.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.models.guided_task import GuidedSession, Routine, RoutineStep
from backend.schemas.guided_task import (
    GuidedSessionDetailOut,
    GuidedSessionListOut,
    GuidedSessionOut,
    RoutineActivityTypeOptionsOut,
    RoutineCreate,
    RoutineDetailOut,
    RoutineLanguageOptionsOut,
    RoutineListOut,
    RoutineOut,
    RoutineUpdate,
)
from backend.services.guided_task.caregiver import Caregiver
from backend.services.guided_task.context import RuntimeContext
from backend.services.guided_task.domain import Decision
from backend.services.guided_task.memory_bridge import GuidedMemoryBridge
from backend.services.guided_task.ports import Escalator, NoopSafetyWatch, SafetyWatch, SessionVoice
from backend.services.guided_task.presentation import Presentation
from backend.services.guided_task.resident_actions import ResidentActions
from backend.services.guided_task.retention import Retention
from backend.services.guided_task.routine_admin import RoutineAdmin, sanitize_completion_gate
from backend.services.guided_task.runtime import Runtime
from backend.services.guided_task.summon import Summon
from backend.services.guided_task.watch import Watch
from backend.services.knowledge.voice_instructions import VoiceInstructionConfig

__all__ = ["GuidedTaskService", "sanitize_completion_gate"]


class GuidedTaskService:
    """Headless guided-task runtime for routines, sessions, and events."""

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
        self._ctx = ctx = RuntimeContext(
            db_factory=db_factory,
            scheduler=scheduler,
            pipeline_executor=pipeline_executor,
            person_location_service=person_location_service,
            zone_service=zone_service,
            bucketizer=bucketizer,
            camera_topology=camera_topology,
            llm_model_registry=llm_model_registry,
            minio_client=minio_client,
            activity_service=activity_service,
            signals_service=signals_service,
            scene_analysis_client=scene_analysis_client,
            companion_surface_service=companion_surface_service,
            ws_manager=ws_manager,
            admin_ws_broadcaster=admin_ws_broadcaster,
            notification_dispatcher=notification_dispatcher,
            conversation_manager=conversation_manager,
            memory_query=memory_query,
            scene_intel=scene_intel,
            embedding_client=embedding_client,
            knowledge_ingestion=knowledge_ingestion,
            voice=voice,
            voice_instructions=voice_instructions,
            safety_watch=safety_watch,
            escalator=escalator,
            settings=settings,
            time_fn=time_fn,
            gate_runner=gate_runner,
            camera_source_resolver=camera_source_resolver,
            event_aggregator=event_aggregator,
        )
        # Dependency order: presentation/retention/memory_bridge are leaves;
        # runtime depends on presentation + memory_bridge; summon/watch/
        # caregiver depend on runtime + presentation; routine_admin is built
        # last (test_run needs summon + presentation).
        self._presentation = Presentation(ctx)
        self._retention = Retention(ctx)
        self._memory_bridge = GuidedMemoryBridge(ctx)
        self._runtime = Runtime(ctx, self._presentation, self._memory_bridge)
        self._resident_actions = ResidentActions(
            ctx, self._presentation, apply_decision=self._runtime.apply_decision
        )
        self._summon = Summon(ctx, self._runtime, self._presentation)
        self._watch = Watch(ctx, self._runtime, self._presentation)
        self._caregiver = Caregiver(ctx, self._runtime, self._presentation)
        self._routine_admin = RoutineAdmin(
            ctx,
            request_start=self._summon.request_start,
            session_out=self._presentation.session_out,
        )

    # ------------------------------------------------------------------
    # Bootstrap setters (write through to the shared context)
    # ------------------------------------------------------------------

    def set_person_location_service(self, person_location_service: Any) -> None:
        self._ctx.person_location_service = person_location_service

    def set_zone_service(self, zone_service: Any) -> None:
        self._ctx.zone_service = zone_service

    def set_bucketizer(self, bucketizer: Any) -> None:
        self._ctx.bucketizer = bucketizer

    def set_safety_watch(self, safety_watch: SafetyWatch | None) -> None:
        self._ctx.safety_watch = safety_watch or NoopSafetyWatch()

    def get_live_session_for_person(self, person_id: str) -> GuidedSession | None:
        return self._ctx.store.get_live_session_for_person(person_id)

    # ------------------------------------------------------------------
    # Test-only shims: a handful of tests reach into these private
    # attributes/methods directly (not module imports, so the "enumerate
    # import-path updates" test policy does not cover them). Kept as thin
    # passthroughs to the collaborator that now owns each one so those
    # tests need zero changes.
    # ------------------------------------------------------------------

    @property
    def _store(self) -> Any:
        return self._ctx.store

    @property
    def _voice_instructions(self) -> VoiceInstructionConfig:
        return self._ctx.voice_instructions

    @property
    def _progress_seen_at(self) -> Any:
        return self._ctx.progress_seen_at

    @property
    def _last_watch_at(self) -> Any:
        return self._ctx.last_watch_at

    async def _speak(self, session: GuidedSession, step: RoutineStep, **kwargs: Any) -> None:
        return await self._presentation.speak(session, step, **kwargs)

    async def _summon_recheck(self, session_id: int, summon_timeout_s: int) -> None:
        return await self._summon.summon_recheck(session_id, summon_timeout_s)

    async def _announce_summon(self, **kwargs: Any) -> None:
        return await self._summon.announce_summon(**kwargs)

    async def _inject_caregiver_message(
        self, session: GuidedSession, routine: Routine, text: str
    ) -> None:
        return await self._caregiver.inject_caregiver_message(session, routine, text)

    # ------------------------------------------------------------------
    # Summon / start
    # ------------------------------------------------------------------

    async def start(
        self,
        routine_id: int,
        person_id: str,
        *,
        execution_id: int | None = None,
        surface_id: str | None = None,
    ) -> GuidedSession:
        return await self._summon.start(
            routine_id, person_id, execution_id=execution_id, surface_id=surface_id
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
        return await self._summon.request_start(
            routine_id,
            person_id,
            execution_id=execution_id,
            surface_id=surface_id,
            require_presence=require_presence,
            summon_timeout_s=summon_timeout_s,
        )

    async def on_session_opened(self, conversation_session_id: int | None = None) -> None:
        return await self._summon.on_session_opened(conversation_session_id)

    # ------------------------------------------------------------------
    # Session runtime
    # ------------------------------------------------------------------

    async def get_active_step(self, session_id: int) -> dict:
        return await self._presentation.get_active_step(session_id)

    async def handle_completion(self, session_id: int, evidence: dict) -> dict:
        return await self._runtime.handle_completion(session_id, evidence)

    async def repeat_step(self, session_id: int) -> dict:
        return await self._resident_actions.repeat_step(session_id)

    async def report_blocked(self, session_id: int, reason: str) -> dict:
        return await self._resident_actions.report_blocked(session_id, reason)

    async def request_help(self, session_id: int, reason: str | None = None) -> dict:
        return await self._resident_actions.request_help(session_id, reason)

    async def on_step_timeout(self, session_id: int) -> Decision:
        return await self._runtime.on_step_timeout(session_id)

    async def resume(self, session_id: int) -> Decision:
        return await self._resident_actions.resume(session_id)

    async def complete(
        self,
        session_id: int,
        outcome: str,
        *,
        actor: str = "system",
    ) -> GuidedSession:
        return await self._runtime.complete(session_id, outcome, actor=actor)

    async def tick(self, now: datetime | None = None) -> None:
        return await self._watch.tick(now)

    # ------------------------------------------------------------------
    # Caregiver takeover
    # ------------------------------------------------------------------

    async def begin_takeover(self, session_id: int) -> GuidedSessionOut:
        return await self._caregiver.begin_takeover(session_id)

    async def caregiver_say(self, session_id: int, text: str) -> GuidedSessionOut:
        return await self._caregiver.caregiver_say(session_id, text)

    async def caregiver_advance(self, session_id: int) -> dict:
        return await self._caregiver.caregiver_advance(session_id)

    async def caregiver_complete(self, session_id: int) -> GuidedSessionOut:
        return await self._caregiver.caregiver_complete(session_id)

    async def release_takeover(self, session_id: int) -> GuidedSessionOut:
        return await self._caregiver.release_takeover(session_id)

    # ------------------------------------------------------------------
    # Presentation / reads
    # ------------------------------------------------------------------

    async def get_detail(self, session_id: int) -> GuidedSessionDetailOut:
        return await self._presentation.get_detail(session_id)

    def list_sessions(
        self,
        *,
        person_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> GuidedSessionListOut:
        return self._presentation.list_sessions(
            person_id=person_id, status=status, limit=limit, offset=offset
        )

    # ------------------------------------------------------------------
    # Routine CRUD / admin test tooling
    # ------------------------------------------------------------------

    def get_language_options(self) -> RoutineLanguageOptionsOut:
        return self._routine_admin.get_language_options()

    def get_activity_type_options(self) -> RoutineActivityTypeOptionsOut:
        return self._routine_admin.get_activity_type_options()

    def list_routines(
        self, *, person_id: str | None = None, limit: int = 20, offset: int = 0
    ) -> RoutineListOut:
        return self._routine_admin.list_routines(person_id=person_id, limit=limit, offset=offset)

    def get_routine_detail(self, routine_id: int) -> RoutineDetailOut:
        return self._routine_admin.get_routine_detail(routine_id)

    def create_routine(self, payload: RoutineCreate) -> RoutineOut:
        return self._routine_admin.create_routine(payload)

    def update_routine(self, routine_id: int, payload: RoutineUpdate) -> RoutineOut:
        return self._routine_admin.update_routine(routine_id, payload)

    def delete_routine(self, routine_id: int) -> None:
        return self._routine_admin.delete_routine(routine_id)

    def replace_steps(self, routine_id: int, steps_in: list[dict]) -> RoutineDetailOut:
        return self._routine_admin.replace_steps(routine_id, steps_in)

    async def test_run(self, routine_id: int, *, surface_id: str | None = None) -> GuidedSessionOut:
        return await self._routine_admin.test_run(routine_id, surface_id=surface_id)

    async def run_gate_preview(
        self,
        *,
        gate_rule_id: int,
        person_id: str | None = None,
        room_name: str | None = None,
        sensor_id: str | None = None,
        profile_name: str = "confirm",
        camera_ids: list[str] | None = None,
        zone_id: int | None = None,
    ) -> Any:
        return await self._routine_admin.run_gate_preview(
            gate_rule_id=gate_rule_id,
            person_id=person_id,
            room_name=room_name,
            sensor_id=sensor_id,
            profile_name=profile_name,
            camera_ids=camera_ids,
            zone_id=zone_id,
        )

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------

    async def prune_retained_data(self) -> dict[str, int]:
        return await self._retention.prune_retained_data()
