"""Routine CRUD and caregiver-admin test tooling (M29)."""

from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable
from typing import Any

from backend.core.exceptions import NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.schemas.guided_task import (
    GuidedSessionOut,
    RoutineCreate,
    RoutineDetailOut,
    RoutineLanguageOptionsOut,
    RoutineListOut,
    RoutineOut,
    RoutineStepOut,
    RoutineUpdate,
)
from backend.services.guided_task.context import RuntimeContext

logger = get_logger(__name__)


def sanitize_completion_gate(gate: dict[str, Any]) -> dict[str, Any]:
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
                "max_cameras": confirm.get("max_cameras"),
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
                "max_cameras": watch.get("max_cameras"),
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


class RoutineAdmin:
    """Routine CRUD (caregiver admin) and gate-graph test/preview tooling."""

    def __init__(
        self,
        ctx: RuntimeContext,
        *,
        request_start: Callable[..., Awaitable[Any]],
        session_out: Callable[[Any], GuidedSessionOut],
    ) -> None:
        self._ctx = ctx
        self._request_start = request_start
        self._session_out = session_out

    def get_language_options(self) -> RoutineLanguageOptionsOut:
        """Configured language codes for the Routine Builder's language select (M27/D15)."""
        names = self._ctx.settings.get("app.language_names", {}) or {}
        return RoutineLanguageOptionsOut(language_names=names)

    def list_routines(
        self, *, person_id: str | None = None, limit: int = 20, offset: int = 0
    ) -> RoutineListOut:
        rows, total = self._ctx.store.list_routines(person_id=person_id, limit=limit, offset=offset)
        items = []
        for r in rows:
            step_count = self._ctx.store.count_steps(r.id)
            out = RoutineOut.model_validate(r, from_attributes=True)
            out = out.model_copy(update={"step_count": step_count})
            items.append(out)
        return RoutineListOut(items=items, total=total)

    def get_routine_detail(self, routine_id: int) -> RoutineDetailOut:
        routine = self._ctx.store.get_routine(routine_id)
        if routine is None:
            raise NotFoundError("Routine", routine_id)
        steps = self._ctx.store.list_steps(routine_id)
        step_count = len(steps)
        routine_out = RoutineOut.model_validate(routine, from_attributes=True)
        routine_out = routine_out.model_copy(update={"step_count": step_count})
        steps_out = [RoutineStepOut.model_validate(s, from_attributes=True) for s in steps]
        return RoutineDetailOut(routine=routine_out, steps=steps_out)

    def create_routine(self, payload: RoutineCreate) -> RoutineOut:
        routine = self._ctx.store.create_routine(**payload.model_dump())
        return RoutineOut.model_validate(routine, from_attributes=True)

    def update_routine(self, routine_id: int, payload: RoutineUpdate) -> RoutineOut:
        data = payload.model_dump(exclude_unset=True)
        updated = self._ctx.store.update_routine(routine_id, **data)
        if updated is None:
            raise NotFoundError("Routine", routine_id)
        step_count = self._ctx.store.count_steps(routine_id)
        out = RoutineOut.model_validate(updated, from_attributes=True)
        return out.model_copy(update={"step_count": step_count})

    def delete_routine(self, routine_id: int) -> None:
        ok = self._ctx.store.delete_routine(routine_id)
        if not ok:
            raise NotFoundError("Routine", routine_id)

    def replace_steps(self, routine_id: int, steps_in: list[dict]) -> RoutineDetailOut:
        routine = self._ctx.store.get_routine(routine_id)
        if routine is None:
            raise NotFoundError("Routine", routine_id)
        ords = [s["ord"] for s in steps_in]
        expected = list(range(len(ords)))
        if sorted(ords) != expected:
            raise ValidationError(f"Step ord values must be contiguous from 0; got {sorted(ords)}")
        for s in steps_in:
            if "completion_gate" in s:
                s["completion_gate"] = sanitize_completion_gate(s["completion_gate"])
        new_steps = self._ctx.store.replace_steps(routine_id, steps_in)
        routine_out = RoutineOut.model_validate(routine, from_attributes=True)
        routine_out = routine_out.model_copy(update={"step_count": len(new_steps)})
        steps_out = [RoutineStepOut.model_validate(s, from_attributes=True) for s in new_steps]
        return RoutineDetailOut(routine=routine_out, steps=steps_out)

    async def test_run(self, routine_id: int, *, surface_id: str | None = None) -> GuidedSessionOut:
        routine = self._ctx.store.get_routine(routine_id)
        if routine is None:
            raise NotFoundError("Routine", routine_id)
        session = await self._request_start(
            routine_id,
            routine.person_id,
            execution_id=None,
            surface_id=surface_id,
            require_presence=False,
        )
        return self._session_out(session)

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

        ctx = self._ctx
        name = "watch" if profile_name == "watch" else "confirm"
        profile = build_default_profile(ctx.settings, name)
        try:
            max_cameras = ctx.settings.as_int("guided_task.vision.max_cameras") or 3
        except Exception:  # noqa: BLE001
            max_cameras = 3

        if ctx.gate_runner is None:
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
        return await ctx.gate_runner.run(
            gate_rule_id=gate_rule_id,
            profile=profile,
            cameras=cameras,
            context=context,
        )
