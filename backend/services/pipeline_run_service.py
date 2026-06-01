"""Read-model service for pipeline run status.

Derives typed ``PipelineRunEnvelope`` objects from existing
``WorkflowExecution`` records and their embedded ``pipeline_data_json``.
No new tables are written; this is a pure read path.

Ingest activity is sourced from ``MediaCache`` (frame_received events) and
``EventLog`` (rule_triggered events) -- the real ingest boundaries that
already exist in the DB (rule 15: no invented counters).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from sqlalchemy.orm import Session, object_session

from backend.core.logging import get_logger
from backend.models.event import EventLog
from backend.models.media_cache import MediaCache
from backend.models.pipeline import PipelineEdge, PipelineStep, WorkflowExecution
from backend.schemas.pipeline_run import (
    DagEdge,
    DagNode,
    IngestActivityEnvelope,
    PipelineRunEnvelope,
)

logger = get_logger(__name__)

_ACTIVE_STATUSES = ("running", "waiting")

_STEP_STATUS_MAP = {
    True: "succeeded",
    False: "failed",
}


class PipelineRunService:
    """Derives pipeline run envelopes from WorkflowExecution records."""

    def __init__(self, db_factory: Callable[[], Session]) -> None:
        self._db_factory = db_factory

    # -- public API -----------------------------------------------------------

    def get_run(self, execution_id: int) -> PipelineRunEnvelope | None:
        """Build a full envelope for one execution; returns None if not found."""
        db = self._db_factory()
        try:
            execution = (
                db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
            )
            if execution is None:
                return None
            return _build_envelope(execution)
        finally:
            db.close()

    def list_active_runs(self) -> list[PipelineRunEnvelope]:
        """Return envelopes for all currently running or waiting executions."""
        db = self._db_factory()
        try:
            executions = (
                db.query(WorkflowExecution)
                .filter(WorkflowExecution.status.in_(_ACTIVE_STATUSES))
                .order_by(WorkflowExecution.started_at.desc())
                .all()
            )
            return [_build_envelope(ex) for ex in executions]
        finally:
            db.close()

    def recent_runs(
        self,
        limit: int = 20,
        status: str | None = None,
    ) -> list[PipelineRunEnvelope]:
        """Return the most recent executions, optionally filtered by status."""
        db = self._db_factory()
        try:
            query = db.query(WorkflowExecution).order_by(WorkflowExecution.started_at.desc())
            if status:
                query = query.filter(WorkflowExecution.status == status)
            executions = query.limit(limit).all()
            return [_build_envelope(ex) for ex in executions]
        finally:
            db.close()

    def list_ingest_activity(self, limit: int = 50) -> list[IngestActivityEnvelope]:
        """Return recent ingest events from MediaCache and EventLog.

        Two event types:
        - ``frame_received``: from MediaCache rows ordered by captured_at desc
        - ``rule_triggered``: from EventLog rows that had a sensor_id and
          were triggered by a sensor event (the real ingest-to-rule boundary)

        Returns the combined list sorted by timestamp desc, capped at *limit*.
        Rule 15: when there is no ingest, returns an explicit empty list.
        """
        db = self._db_factory()
        try:
            half = max(1, limit // 2)

            frames: list[IngestActivityEnvelope] = []
            for mc in (
                db.query(MediaCache)
                .filter(MediaCache.deleted == False)  # noqa: E712
                .order_by(MediaCache.captured_at.desc())
                .limit(half)
                .all()
            ):
                frames.append(
                    IngestActivityEnvelope(
                        id=f"frame-{mc.id}",
                        event_type="frame_received",
                        timestamp=mc.captured_at,
                        sensor_id=mc.sensor_id,
                    )
                )

            triggered: list[IngestActivityEnvelope] = []
            for el in (
                db.query(EventLog)
                .filter(
                    EventLog.sensor_id.isnot(None),
                    EventLog.trigger_type.in_(("sensor_event", "sensor_poll")),
                )
                .order_by(EventLog.timestamp.desc())
                .limit(half)
                .all()
            ):
                triggered.append(
                    IngestActivityEnvelope(
                        id=f"rule-{el.id}",
                        event_type="rule_triggered",
                        timestamp=el.timestamp,
                        sensor_id=el.sensor_id,
                        trigger_type=el.trigger_type,
                        rule_name=el.rule_name,
                    )
                )

            combined = sorted(frames + triggered, key=lambda e: e.timestamp, reverse=True)
            return combined[:limit]
        finally:
            db.close()


# -- helpers ------------------------------------------------------------------


def _build_envelope(execution: WorkflowExecution) -> PipelineRunEnvelope:
    """Derive nodes, edges, and per-step status from a WorkflowExecution."""
    rule = execution.rule
    rule_name = rule.name if rule else f"rule-{execution.rule_id}"
    rule_id = execution.rule_id

    # Build ordered step list from the rule (enabled steps only, by order).
    steps: list[PipelineStep] = []
    if rule is not None:
        steps = sorted(
            [s for s in rule.steps if s.enabled],
            key=lambda s: s.order,
        )

    # Map step timings from pipeline_data_json.
    timing_map: dict[int, dict[str, object]] = {}
    pipeline_data = execution.pipeline_data_json or {}
    for timing in pipeline_data.get("_step_timings", []):
        step_id = timing.get("step_id")
        if step_id is not None:
            timing_map[step_id] = timing

    # Determine per-node status.
    nodes: list[DagNode] = []
    for step in steps:
        status = _step_status(step, execution, timing_map)
        nodes.append(
            DagNode(
                id=str(step.id),
                label=step.label or step.step_type,
                step_type=step.step_type,
                status=status,
            )
        )

    # Authored DAG edges between enabled steps.
    edges: list[DagEdge] = []
    enabled_step_ids = {int(node.id) for node in nodes}
    db = object_session(execution)
    if rule is not None and db is not None:
        for edge in db.query(PipelineEdge).filter(PipelineEdge.rule_id == rule_id).all():
            if edge.source_step_id not in enabled_step_ids or edge.target_step_id not in enabled_step_ids:
                continue
            edges.append(
                DagEdge(
                    source=str(edge.source_step_id),
                    source_handle=edge.source_port,
                    target=str(edge.target_step_id),
                    target_handle=edge.target_port,
                )
            )

    return PipelineRunEnvelope(
        execution_id=execution.id,
        rule_id=rule_id,
        rule_name=rule_name,
        status=execution.status,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        error=execution.error,
        nodes=nodes,
        edges=edges,
    )


_NodeStatus = Literal[
    "pending", "running", "succeeded", "failed", "skipped", "cancelled", "waiting"
]


def _step_status(
    step: PipelineStep,
    execution: WorkflowExecution,
    timing_map: dict[int, dict[str, object]],
) -> _NodeStatus:
    """Derive a single step's display status from timing data and execution state.

    Rule 15: a step with success=False in timing is always "failed", never
    silently coerced to "succeeded" or "pending".
    """
    timing = timing_map.get(step.id)
    if timing is None:
        # Not yet executed.
        if execution.current_step_id == step.id and execution.status == "running":
            return "running"
        if execution.current_step_id == step.id and execution.status == "waiting":
            return "waiting"
        return "pending"

    # Timing entry present: derive from success flag + cancellation flag.
    if timing.get("cancellation_observed"):
        return "cancelled"
    success = timing.get("success")
    if success is True:
        return "succeeded"
    if success is False:
        return "failed"
    # Defensive: success field missing → failed (rule 15 — never fabricate succeeded).
    return "failed"
