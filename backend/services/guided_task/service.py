"""Guided-task lifecycle service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.core.config import SettingNotFoundError, Settings
from backend.core.config import settings as default_settings
from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.core.template import render_template
from backend.integrations.semantic_memory_client import ObservationCreate
from backend.models.guided_task import GuidedSession, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.observability.metrics import location_metrics as guided_metrics
from backend.schemas.guided_task import (
    GuidedSessionDetailOut,
    GuidedSessionEventOut,
    GuidedSessionListOut,
    GuidedSessionOut,
    GuidedSessionStepOut,
    GuidedSessionTurnOut,
    RoutineCreate,
    RoutineDetailOut,
    RoutineListOut,
    RoutineOut,
    RoutineStepOut,
    RoutineUpdate,
)
from backend.schemas.guided_task_ws import GuidedSessionUpdateEvent
from backend.services.guided_task.agent_voice import GUIDED_TASK_DELIVERY_TYPE
from backend.services.guided_task.completion.response import build_evaluators, evaluate_completion
from backend.services.guided_task.domain import Decision, SessionView, StepView
from backend.services.guided_task.policy import resolve_policy, resolve_vision_override
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
from backend.services.interactive_session.prompt_injection import inject_session_prompt

logger = get_logger(__name__)


def sanitize_completion_gate(gate: dict[str, Any]) -> dict[str, Any]:
    import copy

    if not isinstance(gate, dict):
        return gate

    gate = copy.deepcopy(gate)
    vision = gate.get("vision") or gate.get("vision_confirm")
    if isinstance(vision, dict):
        legacy_keys = []
        if "camera_ids" in vision:
            legacy_keys.append("camera_ids")
        if "description" in vision:
            legacy_keys.append("description")

        if legacy_keys:
            logger.warning(
                "legacy_vision_gate_keys_ignored",
                keys=legacy_keys,
            )
            for k in legacy_keys:
                vision.pop(k, None)

        new_vision = {}
        if "gate_graph_rule_id" in vision:
            new_vision["gate_graph_rule_id"] = vision["gate_graph_rule_id"]

        confirm = vision.get("confirm")
        if isinstance(confirm, dict):
            new_vision["confirm"] = {
                "window_s": confirm.get("window_s"),
                "max_frames": confirm.get("max_frames"),
                "min_confidence": confirm.get("min_confidence"),
                "min_interval_s": confirm.get("min_interval_s"),
                "model_id": confirm.get("model_id"),
                "on_max_disagreements": confirm.get("on_max_disagreements"),
            }
        elif "confirm" in vision:
            new_vision["confirm"] = confirm

        watch = vision.get("watch")
        if isinstance(watch, dict):
            new_vision["watch"] = {
                "enabled": watch.get("enabled"),
                "tick_s": watch.get("tick_s"),
                "window_s": watch.get("window_s"),
                "max_frames": watch.get("max_frames"),
                "model_id": watch.get("model_id"),
                "auto_advance": watch.get("auto_advance"),
                "auto_advance_k": watch.get("auto_advance_k"),
            }
        elif "watch" in vision:
            new_vision["watch"] = watch

        for k, v in vision.items():
            if k not in {"confirm", "watch", "gate_graph_rule_id", "camera_ids", "description"}:
                new_vision[k] = v

        gate["vision"] = new_vision
        if "vision_confirm" in gate:
            gate.pop("vision_confirm", None)

    return gate


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
        semantic_memory_client: Any = None,
        memory_query: Any = None,
        voice: SessionVoice | None = None,
        safety_watch: SafetyWatch | None = None,
        escalator: Escalator | None = None,
        settings: Settings | None = None,
        time_fn: Callable[[], datetime] | None = None,
        gate_runner: Any = None,
        camera_source_resolver: Any = None,
        event_aggregator: Any = None,
    ) -> None:
        self._db_factory = db_factory
        self._scheduler = scheduler
        self._pipeline_executor = pipeline_executor
        self._person_location_service = person_location_service
        self._zone_service = zone_service
        self._bucketizer = bucketizer
        self._camera_topology = camera_topology
        self._llm_model_registry = llm_model_registry
        self._minio_client = minio_client
        self._activity_service = activity_service
        self._signals_service = signals_service
        self._scene_analysis_client = scene_analysis_client
        self._companion_surface_service = companion_surface_service
        self._ws_manager = ws_manager
        self._admin_ws_broadcaster = admin_ws_broadcaster
        self._notification_dispatcher = notification_dispatcher
        self._conversation_manager = conversation_manager
        self._semantic_memory_client = semantic_memory_client
        self._memory_query = memory_query
        self._voice = voice or NoopSessionVoice()
        self._safety_watch = safety_watch or NoopSafetyWatch()
        self._escalator = escalator or NoopEscalator()
        self._settings = settings or default_settings
        self._time_fn = time_fn or (lambda: datetime.now(UTC))
        self._store = GuidedTaskStore(db_factory)
        self._gate_runner = gate_runner
        self._camera_source_resolver = camera_source_resolver
        self._event_aggregator = event_aggregator
        self._last_watch_at: dict[tuple[int, int], datetime] = {}
        self._progress_seen_at: dict[tuple[int, int], datetime] = {}

    def set_person_location_service(self, person_location_service: Any) -> None:
        self._person_location_service = person_location_service

    def set_zone_service(self, zone_service: Any) -> None:
        self._zone_service = zone_service

    def set_bucketizer(self, bucketizer: Any) -> None:
        self._bucketizer = bucketizer

    def set_safety_watch(self, safety_watch: SafetyWatch | None) -> None:
        self._safety_watch = safety_watch or NoopSafetyWatch()

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
        """Resolve cameras and run a gate graph once for a preview (VG08 test-run).

        Reuses the same camera cascade and gate runner the live confirm/watch
        paths use. Fail-closed: a missing runner or no cameras returns a
        ``GateVerdict`` with ``complete=False`` rather than raising.
        """
        from types import SimpleNamespace

        from backend.services.guided_task.camera_selection import select_cameras_tagged
        from backend.services.guided_task.gate_runner import (
            GateRunContext,
            GateVerdict,
            build_default_profile,
        )

        name = "watch" if profile_name == "watch" else "confirm"
        profile = build_default_profile(self._settings, name)

        if self._gate_runner is None:
            logger.warning("gate_preview_runner_unavailable", gate_rule_id=gate_rule_id)
            return GateVerdict(
                complete=False,
                confidence=0.0,
                reason="gate_runner_unavailable",
                node_results={},
                cost={"model_calls": 0, "frames": 0, "latency_ms": 0},
                profile=name,
            )

        step_like = SimpleNamespace(camera_ids=camera_ids or [], zone_id=zone_id)
        cameras = await select_cameras_tagged(
            person_id=person_id or "",
            step=step_like,
            zone_service=self._zone_service,
            person_location=self._person_location_service,
            bucketizer=self._bucketizer,
            event_aggregator=self._event_aggregator,
            camera_topology=self._camera_topology,
            identity_resolver=self._identity_ids_for_person,
            camera_source_resolver=self._camera_source_resolver,
            max_cameras=profile.max_frames,
        )
        if not cameras:
            return GateVerdict(
                complete=False,
                confidence=0.0,
                reason="no_cameras",
                node_results={},
                cost={"model_calls": 0, "frames": 0, "latency_ms": 0},
                profile=name,
            )

        context = GateRunContext(
            person_id=person_id,
            room_name=room_name,
            sensor_id=sensor_id,
            session_id=f"preview_{gate_rule_id}",
            step_ord=0,
        )
        return await self._gate_runner.run(
            gate_rule_id=gate_rule_id,
            profile=profile,
            cameras=cameras,
            context=context,
        )

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
            guided_metrics.guided_sessions_total.labels(outcome="summon_timeout").inc()
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

        evidence_with_now = {**evidence, "now": now, "routine": routine}
        evaluators = build_evaluators(
            step.completion_gate,
            activity_service=self._activity_service,
            zone_service=self._zone_service,
            person_location=self._person_location_service,
            bucketizer=self._bucketizer,
            camera_topology=self._camera_topology,
            identity_resolver=self._identity_ids_for_person,
            gate_runner=self._gate_runner,
            camera_source_resolver=self._camera_source_resolver,
            event_aggregator=self._event_aggregator,
            settings=self._settings,
            event_recorder=self._record_vision_confirm_event,
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
                # Resolve the disagreement bound: step -> routine -> global -> default.
                confirm_cfg = (step.completion_gate or {}).get("vision", {}).get("confirm") or {}
                routine_confirm_cfg = (
                    (getattr(routine, "config_json", None) or {})
                    .get("guided_task", {})
                    .get("vision", {})
                    .get("confirm")
                    or {}
                )
                max_disagreements = resolve_vision_override(
                    "max_disagreements",
                    step_cfg=confirm_cfg,
                    routine_cfg=routine_confirm_cfg,
                    settings=self._settings,
                    settings_path="guided_task.vision.confirm.max_disagreements",
                    cast=int,
                    default=2,
                )
                on_max = resolve_vision_override(
                    "on_max_disagreements",
                    step_cfg=confirm_cfg,
                    routine_cfg=routine_confirm_cfg,
                    settings=self._settings,
                    settings_path="guided_task.vision.confirm.on_max_disagreements",
                    cast=str,
                    default="advance",
                )

                # Count disagreements in the DB for this step_ord.
                # Since the current one was just recorded, we fetch all of them.
                from sqlalchemy import select

                from backend.models.guided_task import GuidedSessionEvent

                db = self._db_factory()
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

                if total_disagreements >= max_disagreements:
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
                        await self._apply_decision(
                            session=session,
                            routine=routine,
                            steps=steps,
                            decision=decision,
                            now=now,
                            event_kind="vision_deferred",
                            actor="resident",
                            detail={
                                "completion_reason": "vision_deferred_to_response",
                                "disagreements": total_disagreements,
                                "last_vision_reason": vision_detail.get("reason"),
                                "action": "escalate",
                            },
                            speak_on_advance=False,
                        )
                        return self._decision_descriptor(decision)
                    else:  # "advance"
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
                            event_kind="vision_deferred",
                            actor="resident",
                            detail={
                                "completion_reason": "vision_deferred_to_response",
                                "disagreements": total_disagreements,
                                "last_vision_reason": vision_detail.get("reason"),
                                "action": "advance",
                            },
                            speak_on_advance=False,
                        )
                        return await self._advance_descriptor(session.id, routine, steps, decision)
                else:
                    decision = Decision(
                        kind="wait",
                        next_status=session.status,
                        next_step_ord=session.current_step_ord,
                        attempts=session.attempts,
                        reason=vision_detail.get("reason") or result.reason,
                    )
                    return self._decision_descriptor(decision)

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
            detail={"completion_reason": result.reason, "gates": evaluation.details},
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

    async def begin_takeover(self, session_id: int) -> GuidedSessionOut:
        now = self._now()
        session, routine, steps, step = self._load_runtime(session_id)
        if session.status not in {"active", "waiting", "escalated"}:
            raise ValidationError("Guided session cannot enter caregiver takeover")
        decision = GuidedTaskStateMachine.decide(
            self._session_view(session, steps),
            self._step_view(step),
            "caregiver_takeover",
            resolve_policy(routine, step, self._settings),
            now,
        )
        await self._apply_decision(
            session=session,
            routine=routine,
            steps=steps,
            decision=decision,
            now=now,
            event_kind="caregiver_takeover",
            actor="caregiver",
            detail={"reason": decision.reason},
        )
        updated = self._require_session(session.id)
        await self._broadcast_session_update(
            updated,
            event_kind="takeover_started",
            actor="caregiver",
            detail={"reason": decision.reason},
            at=now,
        )
        logger.info("guided_takeover_started", session_id=session.id, step_ord=step.ord)
        return self._session_out(updated)

    async def caregiver_say(self, session_id: int, text: str) -> GuidedSessionOut:
        now = self._now()
        session, routine, _steps, step = self._load_runtime(session_id)
        if session.status not in {"escalated", "caregiver_takeover"}:
            raise ValidationError("Caregiver messages require escalation or takeover")
        clean_text = text.strip()
        if not clean_text:
            raise ValidationError("Caregiver message cannot be empty")

        conversation_manager = self._conversation_manager
        if conversation_manager is not None:
            conversation_manager.ensure_session(session.id)
            conversation_manager.add_turn(
                session.id,
                "caregiver",
                clean_text,
                metadata={"guided_session_id": session.id, "routine_id": session.routine_id},
            )

        self._store.add_event(
            session_id=session.id,
            at=now,
            kind="caregiver_message",
            step_ord=step.ord,
            actor="caregiver",
            detail={"text": clean_text},
        )
        updated = self._store.update_session(session.id, last_activity_at=now)
        if updated is None:
            raise NotFoundError("Guided session", session.id)

        await self._inject_caregiver_message(updated, routine, clean_text)
        await self._broadcast_session_update(
            updated,
            event_kind="caregiver_message",
            actor="caregiver",
            detail={"step_ord": step.ord},
            at=now,
        )
        logger.info("guided_caregiver_say", session_id=session.id, step_ord=step.ord)
        return self._session_out(updated)

    async def caregiver_advance(self, session_id: int) -> dict:
        now = self._now()
        session, routine, steps, step = self._load_runtime(session_id)
        if session.status not in {"escalated", "caregiver_takeover"}:
            raise ValidationError("Caregiver advance requires escalation or takeover")
        decision = GuidedTaskStateMachine.decide(
            self._session_view(session, steps),
            self._step_view(step),
            "step_completed",
            resolve_policy(routine, step, self._settings),
            now,
            evidence={"confirmed": True, "source": "caregiver"},
        )
        self._store.add_event(
            session_id=session.id,
            at=now,
            kind="step_completed",
            step_ord=step.ord,
            actor="caregiver",
            detail={"confirmed": True, "source": "caregiver"},
        )
        if decision.kind == "complete":
            await self.complete(session.id, "escalated_resolved", actor="caregiver")
        elif decision.kind in {"advance", "skip"}:
            updated_step = self._step_by_ord(steps, decision.next_step_ord)
            self._store.update_session(
                session.id,
                status="caregiver_takeover",
                current_step_ord=decision.next_step_ord,
                attempts=decision.attempts,
                last_activity_at=now,
            )
            self._store.add_event(
                session_id=session.id,
                at=now,
                kind="step_entered",
                step_ord=updated_step.ord,
                actor="caregiver",
                detail={"source": "caregiver"},
            )
        elif decision.kind == "wait":
            return self._decision_descriptor(decision)
        updated = self._require_session(session.id)
        await self._broadcast_session_update(
            updated,
            event_kind="step_completed",
            actor="caregiver",
            detail={"source": "caregiver"},
            at=now,
        )
        return await self._advance_descriptor(session.id, routine, steps, decision)

    async def caregiver_complete(self, session_id: int) -> GuidedSessionOut:
        updated = await self.complete(session_id, "escalated_resolved", actor="caregiver")
        await self._broadcast_session_update(
            updated,
            event_kind="session_completed",
            actor="caregiver",
            detail={"outcome": "escalated_resolved"},
            at=updated.last_activity_at,
        )
        return self._session_out(updated)

    async def release_takeover(self, session_id: int) -> GuidedSessionOut:
        now = self._now()
        session, routine, _steps, step = self._load_runtime(session_id)
        if session.status != "caregiver_takeover":
            raise ValidationError("Guided session is not in caregiver takeover")
        updated = self._store.update_session(session.id, status="active", last_activity_at=now)
        if updated is None:
            raise NotFoundError("Guided session", session.id)
        self._store.add_event(
            session_id=session.id,
            at=now,
            kind="takeover_ended",
            step_ord=step.ord,
            actor="caregiver",
            detail={"status": "active"},
        )
        self._schedule_timeout(updated, routine, step, now)
        await self._broadcast_session_update(
            updated,
            event_kind="takeover_ended",
            actor="caregiver",
            detail={"status": "active"},
            at=now,
        )
        return self._session_out(updated)

    async def get_detail(self, session_id: int) -> GuidedSessionDetailOut:
        session = self._store.get_session(session_id)
        if session is None:
            raise NotFoundError("Guided session", session_id)
        routine, steps = self._load_routine_steps(session.routine_id)
        current_step: GuidedSessionStepOut | None = None
        if steps:
            step = self._step_by_ord(steps, session.current_step_ord)
            current_step = GuidedSessionStepOut(
                ord=step.ord,
                prompt_text=await self._render_step_prompt(session, routine, step),
                completion_gate=step.completion_gate,
                is_safety_critical=step.is_safety_critical,
            )
        events = [
            GuidedSessionEventOut.model_validate(event, from_attributes=True)
            for event in self._store.list_events(session_id=session.id, limit=20)
        ]
        recent_transcript: list[GuidedSessionTurnOut] = []
        conversation_manager = self._conversation_manager
        if conversation_manager is not None:
            recent_transcript = [
                GuidedSessionTurnOut(**turn)
                for turn in conversation_manager.get_recent_turns(session.id, limit=10)
            ]
        return GuidedSessionDetailOut(
            session=self._session_out(session),
            current_step=current_step,
            recent_events=events,
            recent_transcript=recent_transcript,
        )

    # ------------------------------------------------------------------
    # Routine CRUD (Part A)
    # ------------------------------------------------------------------

    def list_routines(
        self, *, person_id: str | None = None, limit: int = 20, offset: int = 0
    ) -> RoutineListOut:
        rows, total = self._store.list_routines(person_id=person_id, limit=limit, offset=offset)
        items = []
        for r in rows:
            step_count = self._store.count_steps(r.id)
            out = RoutineOut.model_validate(r, from_attributes=True)
            out = out.model_copy(update={"step_count": step_count})
            items.append(out)
        return RoutineListOut(items=items, total=total)

    def get_routine_detail(self, routine_id: int) -> RoutineDetailOut:
        routine = self._store.get_routine(routine_id)
        if routine is None:
            raise NotFoundError("Routine", routine_id)
        steps = self._store.list_steps(routine_id)
        step_count = len(steps)
        routine_out = RoutineOut.model_validate(routine, from_attributes=True)
        routine_out = routine_out.model_copy(update={"step_count": step_count})
        steps_out = [RoutineStepOut.model_validate(s, from_attributes=True) for s in steps]
        return RoutineDetailOut(routine=routine_out, steps=steps_out)

    def create_routine(self, payload: RoutineCreate) -> RoutineOut:
        routine = self._store.create_routine(**payload.model_dump())
        return RoutineOut.model_validate(routine, from_attributes=True)

    def update_routine(self, routine_id: int, payload: RoutineUpdate) -> RoutineOut:
        data = payload.model_dump(exclude_unset=True)
        updated = self._store.update_routine(routine_id, **data)
        if updated is None:
            raise NotFoundError("Routine", routine_id)
        step_count = self._store.count_steps(routine_id)
        out = RoutineOut.model_validate(updated, from_attributes=True)
        return out.model_copy(update={"step_count": step_count})

    def delete_routine(self, routine_id: int) -> None:
        ok = self._store.delete_routine(routine_id)
        if not ok:
            raise NotFoundError("Routine", routine_id)

    def replace_steps(self, routine_id: int, steps_in: list[dict]) -> RoutineDetailOut:
        routine = self._store.get_routine(routine_id)
        if routine is None:
            raise NotFoundError("Routine", routine_id)
        ords = [s["ord"] for s in steps_in]
        expected = list(range(len(ords)))
        if sorted(ords) != expected:
            raise ValidationError(f"Step ord values must be contiguous from 0; got {sorted(ords)}")
        for s in steps_in:
            if "completion_gate" in s:
                s["completion_gate"] = sanitize_completion_gate(s["completion_gate"])
        new_steps = self._store.replace_steps(routine_id, steps_in)
        routine_out = RoutineOut.model_validate(routine, from_attributes=True)
        routine_out = routine_out.model_copy(update={"step_count": len(new_steps)})
        steps_out = [RoutineStepOut.model_validate(s, from_attributes=True) for s in new_steps]
        return RoutineDetailOut(routine=routine_out, steps=steps_out)

    async def test_run(self, routine_id: int, *, surface_id: str | None = None) -> GuidedSessionOut:
        routine = self._store.get_routine(routine_id)
        if routine is None:
            raise NotFoundError("Routine", routine_id)
        session = await self.request_start(
            routine_id,
            routine.person_id,
            execution_id=None,
            surface_id=surface_id,
            require_presence=False,
        )
        return self._session_out(session)

    def list_sessions(
        self,
        *,
        person_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> GuidedSessionListOut:
        rows, total = self._store.list_sessions(
            person_id=person_id, status=status, limit=limit, offset=offset
        )
        return GuidedSessionListOut(
            items=[self._session_out(s) for s in rows],
            total=total,
        )

    async def on_step_timeout(self, session_id: int) -> Decision:
        now = self._now()
        session, routine, steps, step = self._load_runtime(session_id)
        if session.status == "caregiver_takeover":
            return Decision(
                kind="noop",
                next_status=session.status,
                next_step_ord=session.current_step_ord,
                attempts=session.attempts,
                reason="caregiver_takeover_paused",
            )

        # Nag suppression (Part B)
        progress_seen_at = self._progress_seen_at.get((session.id, step.ord))
        policy = resolve_policy(routine, step, self._settings)
        if progress_seen_at is not None:
            elapsed = (now - progress_seen_at).total_seconds()
            if elapsed < policy.step_timeout_s:
                logger.info(
                    "nag_suppressed",
                    session_id=session.id,
                    step_ord=step.ord,
                    progress_seen_at=progress_seen_at,
                )
                self._schedule_timeout(session, routine, step, progress_seen_at)
                return Decision(
                    kind="noop",
                    next_status=session.status,
                    next_step_ord=session.current_step_ord,
                    attempts=session.attempts,
                    reason="nag_suppressed",
                )

        decision = GuidedTaskStateMachine.decide(
            self._session_view(session, steps),
            self._step_view(step),
            "timeout_tick",
            policy,
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
            if session.status == "caregiver_takeover":
                continue
            if session.status == "escalated":
                if (
                    tick_at - session.last_activity_at
                ).total_seconds() > self._escalation_grace_s():
                    await self._abandon_escalated_unanswered(session, tick_at)
                continue

            # Evaluate watch profile if enabled
            advanced = False
            if session.status in ("active", "waiting"):
                try:
                    advanced = await self._evaluate_watch(session, routine, steps, step, tick_at)
                except Exception as e:
                    logger.error(
                        "watch_tick_failed",
                        session_id=session.id,
                        step_ord=step.ord,
                        error=str(e),
                        exc_info=True,
                    )
            if advanced:
                continue

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

    async def complete(
        self,
        session_id: int,
        outcome: str,
        *,
        actor: str = "system",
    ) -> GuidedSession:
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
            actor=actor,
            detail={"outcome": outcome},
        )
        guided_metrics.guided_sessions_total.labels(outcome=outcome).inc()
        await self._write_session_observation(updated)
        resume_owning_pipeline(self._pipeline_executor, self._db_factory, updated.execution_id)
        return updated

    async def _inject_caregiver_message(
        self,
        session: GuidedSession,
        routine: Routine,
        text: str,
    ) -> None:
        ws_manager = self._ws_manager
        if ws_manager is None:
            logger.warning(
                "guided_caregiver_say_skipped",
                session_id=session.id,
                reason="ws_manager_unavailable",
            )
            return
        resident_name = self._resident_name(session.person_id)
        prompt = (
            f"Tell {resident_name} the following, in her language and in your own warm voice, "
            f"as if it is your idea: {text}"
        )
        await inject_session_prompt(
            ws_manager,
            prompt=prompt,
            delivery_type=GUIDED_TASK_DELIVERY_TYPE,
            session_id=session.id,
            execution_id=session.execution_id,
            voice_instruction=routine.system_instruction_override or None,
            extra_metadata={"actor": "caregiver", "caregiver_text_hidden": True},
        )

    async def _broadcast_session_update(
        self,
        session: GuidedSession,
        *,
        event_kind: str,
        actor: str | None,
        detail: dict | None,
        at: datetime,
    ) -> None:
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
        payload = event.model_dump(mode="json")
        if self._ws_manager is not None:
            await self._ws_manager.broadcast(payload)
        if self._admin_ws_broadcaster is not None:
            await self._admin_ws_broadcaster(payload)

    async def _abandon_escalated_unanswered(
        self,
        session: GuidedSession,
        at: datetime,
    ) -> None:
        updated = self._store.update_session(
            session.id,
            status="abandoned",
            completed_at=at,
            outcome="escalated_unanswered",
            last_activity_at=at,
        )
        if updated is None:
            raise NotFoundError("Guided session", session.id)
        self._store.add_event(
            session_id=session.id,
            at=at,
            kind="session_abandoned",
            step_ord=session.current_step_ord,
            actor="system",
            detail={"outcome": "escalated_unanswered"},
        )
        guided_metrics.guided_sessions_total.labels(outcome="escalated_unanswered").inc()
        await self._broadcast_session_update(
            updated,
            event_kind="session_abandoned",
            actor="system",
            detail={"outcome": "escalated_unanswered"},
            at=at,
        )
        resume_owning_pipeline(self._pipeline_executor, self._db_factory, updated.execution_id)

    def _escalation_grace_s(self) -> int:
        try:
            return self._settings.as_int("guided_task.escalation_grace_s")
        except SettingNotFoundError:
            return 1800

    def _require_session(self, session_id: int) -> GuidedSession:
        session = self._store.get_session(session_id)
        if session is None:
            raise NotFoundError("Guided session", session_id)
        return session

    def _session_out(self, session: GuidedSession) -> GuidedSessionOut:
        return GuidedSessionOut.model_validate(session, from_attributes=True)

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
        speak_prefix: str | None = None,
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

        if decision.kind == "takeover":
            guided_metrics.guided_takeovers_total.inc()
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

        self._store.add_event(
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
                await self._speak(updated, next_step, is_retry=False, prefix=speak_prefix)
            self._schedule_timeout(updated, routine, next_step, now)
            return

        if decision.kind == "retry":
            guided_metrics.guided_steps_total.labels(result="retried").inc()
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
            guided_metrics.guided_escalations_total.labels(
                kind="emergency" if decision.emergency else "high"
            ).inc()
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

        if decision.kind == "abandon":
            self._store.update_session(
                session.id,
                status=decision.next_status,
                completed_at=now,
                outcome="abandoned",
                last_activity_at=now,
            )
            guided_metrics.guided_sessions_total.labels(outcome="abandoned").inc()
            return

        if decision.kind == "complete":
            guided_metrics.guided_steps_total.labels(result="completed").inc()
            await self.complete(session.id, "completed")

    async def _speak(self, session: GuidedSession, step: RoutineStep, *, is_retry: bool, prefix: str | None = None) -> None:
        routine = self._store.get_routine(session.routine_id)
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

    def _identity_ids_for_person(self, person_id: str) -> set[str]:
        # CTS uses committed identity_id values as HouseholdMember.id values.
        # If a future deployment adds aliases, this resolver is the seam to
        # return all aliases without changing the camera cascade.
        return {person_id}

    def _record_vision_confirm_event(
        self,
        session_id: int,
        step_ord: int | None,
        detail: dict[str, Any],
    ) -> None:
        self._store.add_event(
            session_id=session_id,
            at=self._now(),
            kind="vision_confirm",
            step_ord=step_ord,
            actor="system",
            detail=detail,
        )
        guided_metrics.guided_vision_calls_total.inc()
        if bool(detail.get("uncertain")):
            guided_metrics.guided_vision_uncertain_total.inc()

    async def prune_retained_data(self) -> dict[str, int]:
        days = self._settings.as_int("guided_task.transcript_retention_days")
        cutoff = self._now() - timedelta(days=days)
        session_ids = self._store.list_completed_session_ids_before(cutoff)
        transcript_sessions = 0
        conversation_manager = self._conversation_manager
        if conversation_manager is not None:
            transcript_sessions = conversation_manager.prune_sessions(session_ids)
        events = self._store.prune_events_before(cutoff)
        sessions = self._store.prune_sessions_before(cutoff)
        logger.info(
            "guided_retention_pruned",
            events=events,
            sessions=sessions,
            transcript_sessions=transcript_sessions,
            retention_days=days,
        )
        return {
            "events": events,
            "sessions": sessions,
            "transcript_sessions": transcript_sessions,
        }

    async def _write_session_observation(self, session: GuidedSession) -> None:
        memory = self._semantic_memory_client
        if memory is None:
            logger.info(
                "guided_memory_write_skipped",
                session_id=session.id,
                reason="semantic_memory_unavailable",
            )
            return
        routine = self._store.get_routine(session.routine_id)
        routine_name = routine.name if routine is not None else f"routine {session.routine_id}"
        events = self._store.list_events(session_id=session.id, limit=200)
        completed_steps = sorted(
            {
                event.step_ord
                for event in events
                if event.kind == "step_completed" and event.step_ord is not None
            }
        )
        skipped_steps = sorted(
            {
                event.step_ord
                for event in events
                if event.kind == "step_skipped" and event.step_ord is not None
            }
        )
        stalled_steps = sorted(
            {
                event.step_ord
                for event in events
                if event.kind in {"retry", "step_blocked"} and event.step_ord is not None
            }
        )
        duration_s = 0
        if session.completed_at is not None:
            duration_s = max(0, int((session.completed_at - session.started_at).total_seconds()))
        local_hour = session.started_at.astimezone(
            ZoneInfo(self._settings.as_str("app.timezone"))
        ).strftime("%H:%M")
        description = (
            f"Guided routine '{routine_name}' ended with outcome '{session.outcome}'. "
            f"Duration {duration_s} seconds. Started near local time {local_hour}. "
            f"Completed steps: {completed_steps or 'none'}. "
            f"Skipped steps: {skipped_steps or 'none'}. "
            f"Stalled steps: {stalled_steps or 'none'}."
        )
        try:
            await memory.create_observation(
                ObservationCreate(
                    room_id="guided_task",
                    description=description,
                    object_list=[routine_name],
                    hazard_flags=[],
                    source="guided_task",
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "guided_memory_write_failed",
                session_id=session.id,
                error=str(exc),
            )

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

    async def _evaluate_watch(
        self,
        session: GuidedSession,
        routine: Routine,
        steps: list[RoutineStep],
        step: RoutineStep,
        now: datetime,
    ) -> bool:
        vision_cfg = (
            (step.completion_gate or {}).get("vision") or (step.completion_gate or {}).get("vision_confirm") or {}
        )
        watch_cfg = vision_cfg.get("watch") or {}
        confirm_cfg = vision_cfg.get("confirm") or {}
        routine_cfg = (getattr(routine, "config_json", None) or {}).get("guided_task", {}).get("vision", {})

        r_watch = routine_cfg.get("watch") or {}

        def resolve_val(key: str, default_path: str, type_cast: Callable[[Any], Any], fallback: Any = None) -> Any:
            return resolve_vision_override(
                key,
                step_cfg=watch_cfg,
                routine_cfg=r_watch,
                settings=self._settings,
                settings_path=default_path,
                cast=type_cast,
                default=fallback,
            )

        enabled = resolve_val("enabled", "guided_task.vision.watch.enabled", bool, False)
        if not enabled:
            return False

        tick_s = resolve_val("tick_s", "guided_task.vision.watch.tick_s", float, 20.0)

        # 1. Per-session watch throttle
        last_watch = self._last_watch_at.get((session.id, step.ord))
        if last_watch is not None:
            elapsed = (now - last_watch).total_seconds()
            if elapsed < tick_s:
                return False

        gate_graph_rule_id = vision_cfg.get("gate_graph_rule_id")
        if not gate_graph_rule_id:
            return False

        # Update last watch timestamp
        self._last_watch_at[(session.id, step.ord)] = now

        # Resolve other profile keys
        window_s = resolve_val("window_s", "guided_task.vision.watch.window_s", float, 4.0)
        max_frames = resolve_val("max_frames", "guided_task.vision.watch.max_frames", int, 3)
        model_id = resolve_val("model_id", "guided_task.vision.watch.model_id", str)
        prune_heavy = resolve_val("prune_heavy", "guided_task.vision.watch.prune_heavy", bool, True)

        # Watch has no dedicated min_confidence default; fall back to the confirm
        # threshold (step -> routine -> global -> 0.7) when watch leaves it unset.
        min_confidence = resolve_val("min_confidence", "guided_task.vision.watch.min_confidence", float)
        if min_confidence is None:
            min_confidence = resolve_vision_override(
                "min_confidence",
                step_cfg=confirm_cfg,
                routine_cfg=routine_cfg.get("confirm") or {},
                settings=self._settings,
                settings_path="guided_task.vision.confirm.min_confidence",
                cast=float,
                default=0.7,
            )

        from backend.services.guided_task.gate_runner import GateProfile, GateRunContext
        watch_profile = GateProfile(
            name="watch",
            window_s=window_s,
            max_frames=max_frames,
            min_confidence=min_confidence,
            model_id=model_id,
            prune_heavy=prune_heavy,
        )

        # 2. Resolve cameras
        from backend.services.guided_task.camera_selection import select_cameras_tagged
        cameras = await select_cameras_tagged(
            person_id=session.person_id,
            step=step,
            zone_service=self._zone_service,
            person_location=self._person_location_service,
            bucketizer=self._bucketizer,
            event_aggregator=self._event_aggregator,
            camera_topology=self._camera_topology,
            identity_resolver=self._identity_ids_for_person,
            camera_source_resolver=self._camera_source_resolver,
            max_cameras=max_frames,
        )
        if not cameras:
            return False

        # 3. Run GateGraphRunner
        if self._gate_runner is None:
            logger.warning("guided_watch_gate_runner_unavailable", session_id=session.id)
            return False

        room_name = None
        if self._person_location_service is not None:
            import contextlib
            with contextlib.suppress(Exception):
                location = await self._person_location_service.where_is(session.person_id)
                if location is not None:
                    room_name = getattr(location, "room_name", None)

        context = GateRunContext(
            person_id=session.person_id,
            room_name=room_name,
            sensor_id=None,
            session_id=str(session.id),
            step_ord=int(step.ord),
        )

        verdict = await self._gate_runner.run(
            gate_rule_id=gate_graph_rule_id,
            profile=watch_profile,
            cameras=cameras,
            context=context,
        )

        # Warm/put in cool-off cache for confirm & watch
        cache_key_watch = (str(session.id), int(step.ord), "watch")
        cache_key_confirm = (str(session.id), int(step.ord), "confirm")
        self._gate_runner.cache.put(cache_key_watch, verdict, now=now)
        self._gate_runner.cache.put(cache_key_confirm, verdict, now=now)

        # Emit GuidedSessionEvent(kind="watch")
        formatted_cameras = [{"id": c.id, "source": c.source} for c in cameras]
        formatted_node_results = list(verdict.node_results.values())
        detail = {
            "profile": "watch",
            "gate_graph_rule_id": gate_graph_rule_id,
            "cameras": formatted_cameras,
            "complete": verdict.complete,
            "confidence": verdict.confidence,
            "reason": verdict.reason,
            "node_results": formatted_node_results,
            "cost": verdict.cost,
        }

        self._store.add_event(
            session_id=session.id,
            at=now,
            kind="watch",
            step_ord=step.ord,
            actor="system",
            detail=detail,
        )

        # Part B: Nag-suppression
        if verdict.complete and verdict.confidence >= min_confidence:
            self._progress_seen_at[(session.id, step.ord)] = now

        # Part C: Opt-in conservative auto-advance
        auto_advance = resolve_val("auto_advance", "guided_task.vision.watch.auto_advance", bool, False)
        if auto_advance and not step.is_safety_critical:
            auto_advance_k = resolve_val("auto_advance_k", "guided_task.vision.watch.auto_advance_k", int, 3)
            db = self._db_factory()
            try:
                from sqlalchemy import select

                from backend.models.guided_task import GuidedSessionEvent
                stmt = (
                    select(GuidedSessionEvent)
                    .where(
                        GuidedSessionEvent.session_id == session.id,
                        GuidedSessionEvent.step_ord == step.ord,
                        GuidedSessionEvent.kind == "watch",
                    )
                    .order_by(GuidedSessionEvent.at.desc(), GuidedSessionEvent.id.desc())
                    .limit(auto_advance_k)
                )
                watch_events = list(db.execute(stmt).scalars().all())
            finally:
                db.close()

            if len(watch_events) >= auto_advance_k:
                all_complete = True
                for we in watch_events:
                    we_detail = we.detail or {}
                    we_comp = we_detail.get("complete")
                    we_conf = we_detail.get("confidence", 0.0)
                    if not we_comp or we_conf < min_confidence:
                        all_complete = False
                        break

                if all_complete:
                    decision = GuidedTaskStateMachine.decide(
                        self._session_view(session, steps),
                        self._step_view(step),
                        "step_completed",
                        resolve_policy(routine, step, self._settings),
                        now,
                    )
                    speak_prefix = "I can see you've done that, lovely, now"
                    await self._apply_decision(
                        session=session,
                        routine=routine,
                        steps=steps,
                        decision=decision,
                        now=now,
                        event_kind="step_completed",
                        actor="orchestrator",
                        detail={
                            "completion_reason": "watch_auto_advance",
                            "streak": auto_advance_k,
                            "confidence": verdict.confidence,
                        },
                        speak_prefix=speak_prefix,
                    )
                    logger.info(
                        "guided_watch_auto_advanced",
                        session_id=session.id,
                        step_ord=step.ord,
                        streak=auto_advance_k,
                    )
                    return True
        return False
