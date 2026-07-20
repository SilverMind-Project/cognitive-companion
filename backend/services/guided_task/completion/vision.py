"""Vision-confirm completion evaluator for guided tasks."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from backend.core.logging import get_logger
from backend.services.guided_task.camera_selection import ResolvedCamera, select_cameras_tagged
from backend.services.guided_task.completion.base import CompletionResult
from backend.services.guided_task.domain import (
    CompletionGateConfig,
    VisionGateConfig,
)
from backend.services.guided_task.gate_runner import GateProfile, GateRunContext
from backend.services.guided_task.policy import resolve_vision_override

logger = get_logger(__name__)

VisionEventRecorder = Callable[[int, int | None, dict[str, Any]], None | Awaitable[None]]


class VisionEvaluator:
    """Completion gate driven by a callable gate graph runner."""

    kind = "vision_confirm"

    def __init__(
        self,
        *,
        gate_config: dict | None,
        zone_service: Any | None = None,
        person_location: Any | None = None,
        bucketizer: Any | None = None,
        camera_topology: Any | None = None,
        identity_resolver: Any | None = None,
        gate_runner: Any | None = None,
        camera_source_resolver: Any | None = None,
        event_aggregator: Any | None = None,
        settings: Any | None = None,
        event_recorder: VisionEventRecorder | None = None,
    ) -> None:
        self._gate_config = gate_config or {}
        self._zone_service = zone_service
        self._person_location = person_location
        self._bucketizer = bucketizer
        self._camera_topology = camera_topology
        self._identity_resolver = identity_resolver
        self._gate_runner = gate_runner
        self._camera_source_resolver = camera_source_resolver
        self._event_aggregator = event_aggregator
        self._settings = settings
        self._event_recorder = event_recorder

    async def is_complete(
        self,
        *,
        session: Any,
        step: Any,
        evidence: dict,
    ) -> CompletionResult:
        """Evaluate the gate graph, or reuse a fresh cached verdict.

        A cached negative verdict is still recorded as a disagreement event
        (see below): the cool-off window (``min_interval_s``) bounds how often
        the gate graph actually runs, not whether her assertion is visible to
        the bounded-disagreement count.
        """
        # 1. Resolve the gate rule
        gate_cfg = CompletionGateConfig.model_validate(self._gate_config or {})
        vision_cfg = gate_cfg.vision or VisionGateConfig()
        gate_graph_rule_id = vision_cfg.gate_graph_rule_id

        if not gate_graph_rule_id:
            await self._record(
                session=session,
                step=step,
                cameras=[],
                complete=False,
                confidence=0.0,
                reason="no_gate_graph",
                gate_graph_rule_id=0,
                node_results={},
                cost={"model_calls": 0, "frames": 0, "latency_ms": 0},
            )
            return CompletionResult(False, 0.0, "no_gate_graph")

        # 2. Resolve confirm profile
        confirm_cfg = vision_cfg.confirm

        def resolve_val(
            val: Any | None, default_path: str, type_cast: Callable[[Any], Any], default: Any = None
        ) -> Any:
            return resolve_vision_override(
                val,
                settings=self._settings,
                settings_path=default_path,
                cast=type_cast,
                default=default,
            )

        window_s = resolve_val(confirm_cfg.window_s if confirm_cfg else None, "guided_task.vision.confirm.window_s", float, 20.0)
        max_frames = resolve_val(confirm_cfg.max_frames if confirm_cfg else None, "guided_task.vision.confirm.max_frames", int, 9)
        max_cameras = resolve_val(None, "guided_task.vision.max_cameras", int, 3)
        min_confidence = resolve_val(
            confirm_cfg.min_confidence if confirm_cfg else None, "guided_task.vision.confirm.min_confidence", float, 0.7
        )
        min_interval_s = resolve_val(
            confirm_cfg.min_interval_s if confirm_cfg else None, "guided_task.vision.confirm.min_interval_s", float, 15.0
        )
        model_id = resolve_val(confirm_cfg.model_id if confirm_cfg else None, "guided_task.vision.confirm.model_id", str)

        confirm_profile = GateProfile(
            name="confirm",
            window_s=window_s,
            max_frames=max_frames,
            min_confidence=min_confidence,
            model_id=model_id,
            prune_heavy=False,
        )

        # 3. Resolve cameras
        cameras = await select_cameras_tagged(
            person_id=session.person_id,
            step=step,
            zone_service=self._zone_service,
            person_location=self._person_location,
            bucketizer=self._bucketizer,
            event_aggregator=self._event_aggregator,
            camera_topology=self._camera_topology,
            identity_resolver=self._identity_resolver,
            camera_source_resolver=self._camera_source_resolver,
            max_cameras=max_cameras,
        )
        if not cameras:
            await self._record(
                session=session,
                step=step,
                cameras=[],
                complete=False,
                confidence=0.0,
                reason="no_cameras",
                gate_graph_rule_id=gate_graph_rule_id,
                node_results={},
                cost={"model_calls": 0, "frames": 0, "latency_ms": 0},
            )
            return CompletionResult(False, 0.0, "no_cameras")

        # 4. Cool-off (D28)
        cache_key = (str(session.id), int(step.ord), "confirm")
        now_utc = evidence.get("now") or (
            self._gate_runner._time_fn() if self._gate_runner else datetime.now(UTC)
        )

        if self._gate_runner is not None:
            cached = self._gate_runner.cache.get_fresh(
                cache_key,
                min_interval_s=min_interval_s,
                now=now_utc,
            )
            if cached is not None:
                logger.info(
                    "vision_confirm_cached_verdict_reused",
                    session_id=session.id,
                    step_ord=step.ord,
                    complete=cached.complete,
                    confidence=cached.confidence,
                )
                if not cached.complete:
                    await self._record(
                        session=session,
                        step=step,
                        cameras=cameras,
                        complete=False,
                        confidence=cached.confidence,
                        reason=f"cached:{cached.reason}",
                        gate_graph_rule_id=gate_graph_rule_id,
                        node_results={},
                        cost={"model_calls": 0, "frames": 0, "latency_ms": 0},
                    )
                return CompletionResult(cached.complete, cached.confidence, cached.reason)

        # 5. Run GateGraphRunner
        if self._gate_runner is None:
            logger.warning("guided_completion_gate_runner_unavailable")
            await self._record(
                session=session,
                step=step,
                cameras=cameras,
                complete=False,
                confidence=0.0,
                reason="gate_runner_unavailable",
                gate_graph_rule_id=gate_graph_rule_id,
                node_results={},
                cost={"model_calls": 0, "frames": 0, "latency_ms": 0},
            )
            return CompletionResult(False, 0.0, "gate_runner_unavailable")

        room_name = evidence.get("room_name")
        if not room_name and self._person_location is not None:
            try:
                location = await self._person_location.where_is(session.person_id)
                if location is not None:
                    room_name = getattr(location, "room_name", None)
            except Exception:  # noqa: BLE001
                pass

        sensor_id = evidence.get("sensor_id")

        context = GateRunContext(
            person_id=session.person_id,
            room_name=room_name,
            sensor_id=sensor_id,
            session_id=str(session.id),
            step_ord=int(step.ord),
        )

        verdict = await self._gate_runner.run(
            gate_rule_id=gate_graph_rule_id,
            profile=confirm_profile,
            cameras=cameras,
            context=context,
        )

        # Put in cool-off cache
        self._gate_runner.cache.put(cache_key, verdict, now=now_utc)

        await self._record(
            session=session,
            step=step,
            cameras=cameras,
            complete=verdict.complete,
            confidence=verdict.confidence,
            reason=verdict.reason,
            gate_graph_rule_id=gate_graph_rule_id,
            node_results=verdict.node_results,
            cost=verdict.cost,
        )

        return CompletionResult(verdict.complete, verdict.confidence, verdict.reason)

    async def _record(
        self,
        session: Any,
        step: Any,
        cameras: list[ResolvedCamera],
        complete: bool,
        confidence: float,
        reason: str,
        gate_graph_rule_id: int,
        node_results: dict[str, Any],
        cost: dict[str, Any],
    ) -> None:
        if self._event_recorder is None:
            return

        formatted_cameras = [{"id": c.id, "source": c.source} for c in cameras]
        formatted_node_results = list(node_results.values())

        detail = {
            "profile": "confirm",
            "gate_graph_rule_id": gate_graph_rule_id,
            "cameras": formatted_cameras,
            "complete": complete,
            "confidence": confidence,
            "reason": reason,
            "node_results": formatted_node_results,
            "cost": cost,
        }

        result = self._event_recorder(session.id, getattr(step, "ord", None), detail)
        if inspect.isawaitable(result):
            await result
