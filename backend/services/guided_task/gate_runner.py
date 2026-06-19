"""GateGraphRunner executes a vision gate graph non-durably."""

from __future__ import annotations

import asyncio
import copy
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.models.pipeline import PipelineEdge, PipelineStep, WorkflowExecution
from backend.models.rule import Rule
from backend.services.guided_task.camera_selection import ResolvedCamera
from backend.services.pipeline_data_manager import (
    apply_step_result,
    build_graph_snapshot,
    build_initial_pipeline_data,
    resolve_pipeline_value,
)
from backend.services.pipeline_graph import (
    build_adjacency,
    find_entry_step_ids,
    validate_gate_graph,
)
from backend.services.pipeline_graph_traversal import NodeOutcome, traverse_dag
from backend.steps import StepRegistry
from backend.steps.base import ServiceContainer, TriggerContext

logger = get_logger(__name__)


@dataclass(frozen=True)
class GateRunContext:
    person_id: str | None
    room_name: str | None
    sensor_id: str | None
    session_id: str
    step_ord: int


@dataclass(frozen=True)
class GateProfile:
    name: Literal["confirm", "watch"]
    window_s: float
    max_frames: int
    min_confidence: float
    model_id: str | None = None  # overrides VLM node model when set
    prune_heavy: bool = False  # watch prunes heavy nodes by default

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "window_s": self.window_s,
            "max_frames": self.max_frames,
            "min_confidence": self.min_confidence,
            "model_id": self.model_id,
            "prune_heavy": self.prune_heavy,
        }


@dataclass(frozen=True)
class GateVerdict:
    complete: bool
    confidence: float
    reason: str
    node_results: dict[str, Any]
    cost: dict[str, Any]
    profile: str


@dataclass
class _CachedVerdict:
    verdict: GateVerdict
    at: datetime


class _CoolOffCache:
    def __init__(self) -> None:
        # Key is (session_id, step_ord, profile_name)
        self._cache: dict[tuple[str, int, str], _CachedVerdict] = {}

    def get_fresh(
        self,
        key: tuple[str, int, str],
        *,
        min_interval_s: float,
        now: datetime,
    ) -> GateVerdict | None:
        cached = self._cache.get(key)
        if not cached:
            return None
        elapsed = (now - cached.at).total_seconds()
        if elapsed < min_interval_s:
            return cached.verdict
        return None

    def put(
        self,
        key: tuple[str, int, str],
        verdict: GateVerdict,
        *,
        now: datetime,
    ) -> None:
        self._cache[key] = _CachedVerdict(verdict=verdict, at=now)


@dataclass
class _SyntheticRule:
    name: str


@dataclass
class _SyntheticExecution:
    id: str  # f"gate_{session_id}_{step_ord}_{profile}"
    rule_id: int  # the gate rule id
    rule: _SyntheticRule  # exposes .name


def _synthetic_trigger(*, room_name: str | None, sensor_id: str | None) -> TriggerContext:
    """A minimal TriggerContext for read-only perception steps."""
    return TriggerContext(
        trigger_type="sensor_event",
        sensor_id=sensor_id,
        room_name=room_name,
        media_paths=[],
        media_type="image",
        webhook_payload=None,
    )


def _extract_cost_hint(
    step: PipelineStep, pipeline_data: dict, profile_model_id: str | None
) -> dict[str, Any]:
    hint: dict[str, Any] = {}
    config = step.config_json or {}

    if step.step_type == "llm_call":
        model_id = config.get("model_id")
        if profile_model_id and config.get("use_profile_model") is True:
            model_id = profile_model_id
        if model_id:
            hint["model_id"] = model_id

        frames_path = config.get("cts_frames_path") or config.get("pipeline_image_path")
        if frames_path:
            try:
                resolved = resolve_pipeline_value(pipeline_data, frames_path)
                if isinstance(resolved, list):
                    hint["image_count"] = len(resolved)
            except Exception:  # noqa: BLE001
                pass

    elif step.step_type == "scene_analysis":
        frames_path = config.get("cts_frames_path")
        if frames_path:
            try:
                resolved = resolve_pipeline_value(pipeline_data, frames_path)
                if isinstance(resolved, list):
                    hint["image_count"] = len(resolved)
            except Exception:  # noqa: BLE001
                pass

    return hint


class GateGraphRunner:
    def __init__(
        self,
        *,
        services: ServiceContainer,
        db_factory: Callable[[], Session],  # read-only: load gate rule steps/edges
        settings: Any = settings,
        time_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
        node_timeout_s: float | None = None,  # from guided_task.vision.gate_node_timeout_s
    ) -> None:
        self._services = services
        self._db_factory = db_factory
        self._settings = settings
        self._time_fn = time_fn

        if node_timeout_s is None:
            try:
                self._node_timeout_s = settings.as_float("guided_task.vision.gate_node_timeout_s")
            except Exception:  # noqa: BLE001
                self._node_timeout_s = 30.0
        else:
            self._node_timeout_s = node_timeout_s

        self.cache = _CoolOffCache()

    async def run(
        self,
        *,
        gate_rule_id: int,
        profile: GateProfile,  # confirm | watch params (resolved)
        cameras: list[ResolvedCamera],  # from select_cameras_tagged (VG3)
        context: GateRunContext,  # person_id, room_name, sensor_id, session_id, step_ord
    ) -> GateVerdict:
        start_time = time.perf_counter()

        # 1. Load the graph (one read-only DB query)
        with self._db_factory() as db:
            rule = db.query(Rule).filter(Rule.id == gate_rule_id).first()
            if not rule:
                return GateVerdict(
                    complete=False,
                    confidence=0.0,
                    reason="rule_not_found",
                    node_results={},
                    cost={
                        "model_calls": 0,
                        "frames": 0,
                        "latency_ms": int((time.perf_counter() - start_time) * 1000),
                    },
                    profile=profile.name,
                )
            if not rule.enabled:
                return GateVerdict(
                    complete=False,
                    confidence=0.0,
                    reason="rule_disabled",
                    node_results={},
                    cost={
                        "model_calls": 0,
                        "frames": 0,
                        "latency_ms": int((time.perf_counter() - start_time) * 1000),
                    },
                    profile=profile.name,
                )

            steps = (
                db.query(PipelineStep)
                .filter(PipelineStep.rule_id == gate_rule_id, PipelineStep.enabled.is_(True))
                .order_by(PipelineStep.order)
                .all()
            )

            edges = db.query(PipelineEdge).filter(PipelineEdge.rule_id == gate_rule_id).all()

            rule_name = rule.name

        # 2. Defense-in-depth gate_safe check
        StepRegistry.discover()
        unsafe_steps = []
        for step in steps:
            handler = StepRegistry.get(step.step_type)
            if not handler or not handler.metadata().gate_safe:
                unsafe_steps.append(step)

        if unsafe_steps:
            logger.error(
                "gate_runner_refused",
                rule_id=gate_rule_id,
                reason="non_gate_safe_step",
                unsafe_step_types=[s.step_type for s in unsafe_steps],
            )
            return GateVerdict(
                complete=False,
                confidence=0.0,
                reason="non_gate_safe_step",
                node_results={},
                cost={
                    "model_calls": 0,
                    "frames": 0,
                    "latency_ms": int((time.perf_counter() - start_time) * 1000),
                },
                profile=profile.name,
            )

        # Validate graph topology using validate_gate_graph
        def get_meta(step_type: str):
            StepRegistry.discover()
            handler = StepRegistry.get(step_type)
            return handler.metadata() if handler else None

        errors = validate_gate_graph(steps, edges, step_metadata=get_meta, gate_safe_only=False)
        if errors:
            logger.error(
                "gate_runner_refused",
                rule_id=gate_rule_id,
                reason="invalid_graph",
                errors=errors,
            )
            return GateVerdict(
                complete=False,
                confidence=0.0,
                reason="invalid_graph",
                node_results={},
                cost={
                    "model_calls": 0,
                    "frames": 0,
                    "latency_ms": int((time.perf_counter() - start_time) * 1000),
                },
                profile=profile.name,
            )

        # 3. Seed pipeline_data
        local_tz = ZoneInfo(self._settings.as_str("app.timezone"))
        now_utc = self._time_fn()
        now_local = now_utc.astimezone(local_tz)

        pipeline_data = build_initial_pipeline_data(
            trigger_type="sensor_event",
            sensor_id=context.sensor_id,
            room_name=context.room_name,
            media_paths=[],
            media_type="image",
            webhook_payload=None,
            now_utc=now_utc,
            now_local=now_local,
            timezone_name=str(local_tz),
        )

        pipeline_data["_profile"] = profile.as_dict()
        pipeline_data["_cameras"] = [{"id": c.id, "source": c.source} for c in cameras]

        def get_output_ports(st: str) -> tuple[str, ...]:
            StepRegistry.discover()
            h = StepRegistry.get(st)
            return h.metadata().output_ports if h else ("main",)

        pipeline_data["_graph"] = build_graph_snapshot(steps, edges, get_output_ports)

        # Prepare adjacency and entry_ids
        adjacency = build_adjacency(edges)
        entry_ids = find_entry_step_ids({s.id for s in steps}, edges)
        node_ids = {s.id for s in steps}
        step_by_id = {s.id: s for s in steps}

        node_results: dict[str, Any] = {}
        cost = {
            "model_calls": 0,
            "frames": 0,
            "latency_ms": 0,
        }

        async def execute_node(node_id: int) -> NodeOutcome:
            step = step_by_id[node_id]
            label = step.label or step.step_type

            # 4.b. Heavy pruning (D24)
            if profile.prune_heavy and step.config_json and step.config_json.get("heavy") is True:
                logger.info(
                    "gate_node_pruned",
                    node_id=node_id,
                    step_type=step.step_type,
                    label=label,
                )
                node_results[label] = {
                    "type": step.step_type,
                    "label": label,
                    "ports": [],
                    "pruned": True,
                }
                return NodeOutcome(active_ports=frozenset())

            # Get step handler
            handler = StepRegistry.get(step.step_type)
            if not handler:
                logger.error(
                    "gate_node_failed",
                    node_id=node_id,
                    reason="handler_not_found",
                    step_type=step.step_type,
                )
                node_results[label] = {
                    "type": step.step_type,
                    "label": label,
                    "ports": [],
                    "error": "handler_not_found",
                }
                return NodeOutcome(active_ports=frozenset())

            # VLM model override
            step_to_execute = step
            if (
                profile.model_id
                and step.step_type == "llm_call"
                and step.config_json
                and step.config_json.get("use_profile_model") is True
            ):
                step_to_execute = copy.copy(step)
                step_to_execute.config_json = copy.deepcopy(step.config_json)
                step_to_execute.config_json["model_id"] = profile.model_id

            # 4.c. Per-node timeout
            try:
                exec_id = f"gate_{context.session_id}_{context.step_ord}_{profile.name}"
                syn_exec = _SyntheticExecution(
                    id=exec_id,
                    rule_id=gate_rule_id,
                    rule=_SyntheticRule(name=rule_name),
                )
                syn_trigger = _synthetic_trigger(
                    room_name=context.room_name,
                    sensor_id=context.sensor_id,
                )

                result = await asyncio.wait_for(
                    handler.execute(
                        step_to_execute,
                        cast(WorkflowExecution, syn_exec),
                        pipeline_data,
                        syn_trigger,
                        self._services,
                    ),
                    timeout=self._node_timeout_s,
                )

                # 4.d. Merge output
                apply_step_result(
                    pipeline_data,
                    step.id,
                    step.step_type,
                    label,
                    result.data,
                )

                # Update cost tracking
                if step.step_type == "media_window_poll":
                    cost["frames"] += len(result.data.get("images", []))
                elif step.step_type == "llm_call":
                    cost["model_calls"] += 1

                # 4.e. Record node result summary
                cost_hint = _extract_cost_hint(step_to_execute, pipeline_data, profile.model_id)
                node_results[label] = {
                    "type": step.step_type,
                    "label": label,
                    "ports": list(result.output_ports),
                    **cost_hint,
                }

                return NodeOutcome(
                    active_ports=frozenset(result.output_ports),
                    stop=False,
                )

            except Exception as exc:
                logger.exception(
                    "gate_node_failed",
                    node_id=node_id,
                    step_type=step.step_type,
                    label=label,
                    error=str(exc),
                )
                node_results[label] = {
                    "type": step.step_type,
                    "label": label,
                    "ports": [],
                    "error": str(exc),
                }
                return NodeOutcome(active_ports=frozenset())

        async def on_skip(node_id: int) -> None:
            skipped_step = step_by_id[node_id]
            label = skipped_step.label or skipped_step.step_type
            logger.info(
                "gate_node_skipped",
                node_id=node_id,
                step_type=skipped_step.step_type,
                label=label,
            )
            node_results[label] = {
                "type": skipped_step.step_type,
                "label": label,
                "ports": [],
                "skipped": True,
            }

        # 4. Traverse
        await traverse_dag(
            node_ids=node_ids,
            adjacency=adjacency,
            entry_ids=entry_ids,
            execute_node=execute_node,
            on_skip=on_skip,
        )

        # 5. Extract the verdict
        verdict_steps = [s for s in steps if s.step_type == "gate_verdict"]
        if verdict_steps:
            verdict_step = verdict_steps[0]
            verdict_label = verdict_step.label or verdict_step.step_type

            step_output = pipeline_data.get("steps", {}).get(verdict_label, {}).get("outputs", {})
            verdict_data = step_output.get("gate_verdict")

            if verdict_data and isinstance(verdict_data, dict):
                complete = bool(verdict_data.get("complete", False))
                confidence = float(verdict_data.get("confidence", 0.0))
                reason = str(verdict_data.get("reason", "gate_verdict"))

                cost["latency_ms"] = int((time.perf_counter() - start_time) * 1000)

                logger.info(
                    "gate_verdict_resolved",
                    rule_id=gate_rule_id,
                    complete=complete,
                    confidence=confidence,
                    reason=reason,
                    profile=profile.name,
                )
                return GateVerdict(
                    complete=complete,
                    confidence=confidence,
                    reason=reason,
                    node_results=node_results,
                    cost=cost,
                    profile=profile.name,
                )

        cost["latency_ms"] = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "gate_verdict_no_verdict",
            rule_id=gate_rule_id,
            profile=profile.name,
        )
        return GateVerdict(
            complete=False,
            confidence=0.0,
            reason="no_verdict",
            node_results=node_results,
            cost=cost,
            profile=profile.name,
        )
