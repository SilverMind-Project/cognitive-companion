"""Background tick: vision watch, resume-grace, and safety dispatch (M29).

Depends on ``runtime.py`` (``apply_decision``) and ``presentation.py``
(``broadcast_session_update``), both already-built collaborators injected
by the façade.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from backend.core.config import SettingNotFoundError
from backend.core.logging import get_logger
from backend.core.template import render_template
from backend.models.guided_task import GuidedSession, Routine, RoutineStep
from backend.services.guided_task.context import RuntimeContext
from backend.services.guided_task.policy import resolve_policy, resolve_vision_override
from backend.services.guided_task.presentation import Presentation
from backend.services.guided_task.runtime import Runtime
from backend.services.guided_task.state_machine import GuidedTaskStateMachine

logger = get_logger(__name__)


class Watch:
    """Live session tick: vision watch, resume-grace abandon, safety events."""

    def __init__(
        self,
        ctx: RuntimeContext,
        runtime: Runtime,
        presentation: Presentation,
    ) -> None:
        self._ctx = ctx
        self._runtime = runtime
        self._presentation = presentation

    async def tick(self, now: datetime | None = None) -> None:
        ctx = self._ctx
        tick_at = now or ctx.now()
        for session in ctx.store.list_live_sessions():
            routine, steps = ctx.load_routine_steps(session.routine_id)
            step = ctx.step_by_ord(steps, session.current_step_ord)
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

            policy = resolve_policy(routine, step, ctx.settings)
            if (tick_at - session.last_activity_at).total_seconds() > policy.resume_grace_s:
                decision = GuidedTaskStateMachine.decide(
                    ctx.session_view(session, steps),
                    ctx.step_view(step),
                    "resume",
                    policy,
                    tick_at,
                )
                await self._runtime.apply_decision(
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

            for safety_event in await ctx.safety_watch.evaluate(session=session):
                decision = GuidedTaskStateMachine.decide(
                    ctx.session_view(session, steps),
                    ctx.step_view(step),
                    "safety_event",
                    policy,
                    tick_at,
                    evidence=safety_event,
                )
                await self._runtime.apply_decision(
                    session=session,
                    routine=routine,
                    steps=steps,
                    decision=decision,
                    now=tick_at,
                    event_kind="safety_event",
                    actor="system",
                    detail=safety_event,
                )

    async def _abandon_escalated_unanswered(
        self,
        session: GuidedSession,
        at: datetime,
    ) -> None:
        ctx = self._ctx
        updated = ctx.mark_abandoned(session.id, now=at, outcome="escalated_unanswered")
        ctx.store.add_event(
            session_id=session.id,
            at=at,
            kind="session_abandoned",
            step_ord=session.current_step_ord,
            actor="system",
            detail={"outcome": "escalated_unanswered"},
        )
        await self._presentation.broadcast_session_update(
            updated,
            event_kind="session_abandoned",
            actor="system",
            detail={"outcome": "escalated_unanswered"},
            at=at,
        )

    def _escalation_grace_s(self) -> int:
        try:
            return self._ctx.settings.as_int("guided_task.escalation_grace_s")
        except SettingNotFoundError:
            return 1800

    async def _evaluate_watch(
        self,
        session: GuidedSession,
        routine: Routine,
        steps: list[RoutineStep],
        step: RoutineStep,
        now: datetime,
    ) -> bool:
        ctx = self._ctx
        vision_cfg = (
            (step.completion_gate or {}).get("vision")
            or (step.completion_gate or {}).get("vision_confirm")
            or {}
        )
        watch_cfg = vision_cfg.get("watch") or {}
        confirm_cfg = vision_cfg.get("confirm") or {}
        routine_cfg = (
            (getattr(routine, "config_json", None) or {}).get("guided_task", {}).get("vision", {})
        )

        r_watch = routine_cfg.get("watch") or {}

        def resolve_val(
            key: str, default_path: str, type_cast: Callable[[Any], Any], fallback: Any = None
        ) -> Any:
            return resolve_vision_override(
                key,
                step_cfg=watch_cfg,
                routine_cfg=r_watch,
                settings=ctx.settings,
                settings_path=default_path,
                cast=type_cast,
                default=fallback,
            )

        enabled = resolve_val("enabled", "guided_task.vision.watch.enabled", bool, False)
        if not enabled:
            return False

        tick_s = resolve_val("tick_s", "guided_task.vision.watch.tick_s", float, 20.0)

        # 1. Per-session watch throttle
        last_watch = ctx.last_watch_at.get((session.id, step.ord))
        if last_watch is not None:
            elapsed = (now - last_watch).total_seconds()
            if elapsed < tick_s:
                return False

        gate_graph_rule_id = vision_cfg.get("gate_graph_rule_id")
        if not gate_graph_rule_id:
            return False

        # Update last watch timestamp
        ctx.last_watch_at[(session.id, step.ord)] = now

        # Resolve other profile keys
        window_s = resolve_val("window_s", "guided_task.vision.watch.window_s", float, 4.0)
        max_frames = resolve_val("max_frames", "guided_task.vision.watch.max_frames", int, 3)
        max_cameras = resolve_val("max_cameras", "guided_task.vision.max_cameras", int, 3)
        model_id = resolve_val("model_id", "guided_task.vision.watch.model_id", str)
        prune_heavy = resolve_val("prune_heavy", "guided_task.vision.watch.prune_heavy", bool, True)

        # Watch has no dedicated min_confidence default; fall back to the confirm
        # threshold (step -> routine -> global -> 0.7) when watch leaves it unset.
        min_confidence = resolve_val(
            "min_confidence", "guided_task.vision.watch.min_confidence", float
        )
        if min_confidence is None:
            min_confidence = resolve_vision_override(
                "min_confidence",
                step_cfg=confirm_cfg,
                routine_cfg=routine_cfg.get("confirm") or {},
                settings=ctx.settings,
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
            zone_service=ctx.zone_service,
            person_location=ctx.person_location_service,
            bucketizer=ctx.bucketizer,
            event_aggregator=ctx.event_aggregator,
            camera_topology=ctx.camera_topology,
            identity_resolver=ctx.identity_ids_for_person,
            camera_source_resolver=ctx.camera_source_resolver,
            max_cameras=max_cameras,
        )
        if not cameras:
            return False

        # 3. Run GateGraphRunner
        if ctx.gate_runner is None:
            logger.warning("guided_watch_gate_runner_unavailable", session_id=session.id)
            return False

        room_name = None
        if ctx.person_location_service is not None:
            import contextlib

            with contextlib.suppress(Exception):
                location = await ctx.person_location_service.where_is(session.person_id)
                if location is not None:
                    room_name = getattr(location, "room_name", None)

        context = GateRunContext(
            person_id=session.person_id,
            room_name=room_name,
            sensor_id=None,
            session_id=str(session.id),
            step_ord=int(step.ord),
        )

        verdict = await ctx.gate_runner.run(
            gate_rule_id=gate_graph_rule_id,
            profile=watch_profile,
            cameras=cameras,
            context=context,
        )

        # Warm the watch cool-off slot unconditionally (the watch throttle needs
        # it); warm the confirm slot only on a positive verdict. A negative
        # watch verdict answering her actual "done" is the exact inversion of
        # D28's cache rationale (avoid dropping a valid "done"), so it must
        # never be reused as a confirm answer (G3).
        cache_key_watch = (str(session.id), int(step.ord), "watch")
        cache_key_confirm = (str(session.id), int(step.ord), "confirm")
        ctx.gate_runner.cache.put(cache_key_watch, verdict, now=now)
        if verdict.complete and verdict.confidence >= min_confidence:
            ctx.gate_runner.cache.put(cache_key_confirm, verdict, now=now)

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

        ctx.store.add_event(
            session_id=session.id,
            at=now,
            kind="watch",
            step_ord=step.ord,
            actor="system",
            detail=detail,
        )

        # Part B: Nag-suppression
        if verdict.complete and verdict.confidence >= min_confidence:
            ctx.progress_seen_at[(session.id, step.ord)] = now

        # Part C: Opt-in conservative auto-advance
        auto_advance = resolve_val(
            "auto_advance", "guided_task.vision.watch.auto_advance", bool, False
        )
        if auto_advance and not step.is_safety_critical:
            auto_advance_k = resolve_val(
                "auto_advance_k", "guided_task.vision.watch.auto_advance_k", int, 3
            )
            db = ctx.db_factory()
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
                        ctx.session_view(session, steps),
                        ctx.step_view(step),
                        "step_completed",
                        resolve_policy(routine, step, ctx.settings),
                        now,
                    )
                    speak_prefix = render_template(
                        ctx.voice_instructions.guided_task_auto_advance_prefix, {}
                    )
                    await self._runtime.apply_decision(
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
