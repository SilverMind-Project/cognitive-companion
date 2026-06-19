"""Composable pipeline executor.

Orchestrates step-by-step execution of rule pipelines using the
:class:`StepRegistry` plugin system.  Each step type is a self-contained
handler registered at startup.  The executor is responsible only for
sequencing, branching, wait/resume, error handling, per-step timing, and
enforcing per-rule execution timeouts.

## Concurrency Control and Locking Strategy

The pipeline executor uses a **hybrid locking strategy** to protect
WorkflowExecution records from race conditions during concurrent access:

### Optimistic Locking (Default)
- Used for: Pipeline step updates to `pipeline_data_json`
- Mechanism: Version column with automatic conflict detection
- Behavior: Retry with exponential backoff on `StaleDataError`
- Configuration: MAX_RETRIES=3, BASE_DELAY=0.1s
- Function: `_update_pipeline_data_with_retry()`
- Rationale: Low contention, high throughput, retries acceptable

### Pessimistic Locking (Critical Sections)
- Used for: Status transitions and exclusive state changes
- Mechanism: `SELECT ... FOR UPDATE` row-level locks
- Behavior: Block concurrent access until transaction commits
- Critical sections:
  1. **Resume operations** (`resume()`): Prevents concurrent resume attempts
     (manual + scheduled) from racing on status transition waiting->running
  2. **Timeout handling** (`_handle_timeout()`): Ensures exclusive access
     when marking execution as failed after cancellation, preventing conflicts
     with the cancelled coroutine's uncommitted changes
  3. **Status transitions**: Any operation that changes execution.status
     requires exclusive access to prevent invalid state transitions

### When to Use Each Strategy

| Operation | Strategy | Rationale |
|-----------|----------|-----------|
| Pipeline step data updates | Optimistic | Fast, low contention |
| Status transitions | Pessimistic | Critical state, must not race |
| Resume from wait | Pessimistic | Prevent duplicate resumes |
| Timeout handling | Pessimistic | Clean up cancelled coroutine |
| Normal step execution | Optimistic | High throughput needed |

### Lock Ordering and Deadlock Prevention
- Always acquire WorkflowExecution lock before EventLog lock
- Keep transactions short (single status update + commit)
- Use statement_timeout in PostgreSQL to prevent indefinite waits
- Monitor lock contention via SQLAlchemy event listeners (see database.py)

### MutableDict and Nested Mutations
The `pipeline_data_json` column uses `MutableDict.as_mutable(JSON)` which
tracks top-level mutations (`__setitem__`, `update`) but NOT nested mutations.
For nested updates like `pipeline_data["_pipeline"]["completed_at"]`, use
`flag_modified(execution, "pipeline_data_json")` to mark the column dirty.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm.exc import StaleDataError

from backend.core.config import settings
from backend.core.exceptions import ValidationError
from backend.core.logging import get_logger
from backend.models.event import EventLog
from backend.models.pipeline import PipelineEdge, PipelineStep, WorkflowExecution
from backend.models.rule import Rule
from backend.schemas.pipeline_ws import (
    EdgeRef,
    PipelineCancelledEvent,
    PipelineCompletedEvent,
    PipelineFailedEvent,
    PipelineStartedEvent,
    PipelineWaitingEvent,
    StepCompletedEvent,
    StepNodeRef,
    StepStartedEvent,
)
from backend.services.pipeline_data_manager import (
    apply_step_result,
    build_graph_snapshot,
    build_initial_pipeline_data,
    copy_pipeline_snapshot,
)
from backend.services.pipeline_graph import (
    build_adjacency,
    find_descendants,
    find_entry_step_ids,
    validate_graph,
)
from backend.services.pipeline_graph_traversal import NodeOutcome, traverse_dag
from backend.steps import StepRegistry
from backend.steps.base import ServiceContainer, StepResult, TriggerContext

logger = get_logger(__name__)

# Optimistic locking retry configuration
MAX_RETRIES = 3
BASE_DELAY = 0.1  # seconds


class PipelineExecutor:
    """Execute a rule's composable pipeline steps in sequence.

    Each step handler is looked up from the :class:`StepRegistry` and
    receives a :class:`ServiceContainer` with all available services.

    Timing data is written into ``pipeline_data_json`` under two keys:

    * ``_pipeline`` - ``{"started_at": ISO, "completed_at": ISO | null}``
    * ``_step_timings`` - list of per-step dicts with ``started_at``,
      ``completed_at``, ``elapsed_seconds``, and ``success``.

    When a rule sets ``execution_timeout_minutes > 0`` the entire pipeline
    (excluding wait periods) is cancelled if it exceeds that duration and the
    execution is marked ``"failed"`` with a descriptive error.
    """

    def __init__(
        self,
        db_session_factory,
        person_tracking=None,
        person_id_client=None,
        notification_dispatcher=None,
        ha_client=None,
        event_aggregator=None,
        scheduler=None,
        llm_model_registry=None,
        scene_analysis_client=None,
        daily_report_service=None,
        semantic_memory_client=None,
        interactive_response_service=None,
        memory_query=None,
        scene_intel=None,
        activity=None,
        signals=None,
        knowledge_delivery=None,
        minio_client=None,
        rules_engine=None,
        event_publisher: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        camera_source_resolver=None,
    ) -> None:
        self._services = ServiceContainer(
            db_factory=db_session_factory,
            person_tracking=person_tracking,
            person_id_client=person_id_client,
            notification_dispatcher=notification_dispatcher,
            ha_client=ha_client,
            event_aggregator=event_aggregator,
            scheduler=scheduler,
            llm_model_registry=llm_model_registry,
            scene_analysis_client=scene_analysis_client,
            daily_report_service=daily_report_service,
            semantic_memory_client=semantic_memory_client,
            interactive_response_service=interactive_response_service,
            memory_query=memory_query,
            scene_intel=scene_intel,
            activity=activity,
            signals=signals,
            knowledge_delivery=knowledge_delivery,
            minio_client=minio_client,
            camera_source_resolver=camera_source_resolver,
        )
        self._rules_engine = rules_engine
        self._event_publisher = event_publisher
        # Monotonic sequence counter for ordering events across executions.
        self._event_sequence = 0

    # Expose scheduler for injection after construction
    @property
    def _scheduler(self):
        return self._services.scheduler

    @_scheduler.setter
    def _scheduler(self, value):
        self._services.scheduler = value

    # Expose the CTS bucketizer for injection after CTS bootstrap (it is built
    # by CTSRuntime, which is constructed after this executor).
    @property
    def bucketizer(self):
        return self._services.bucketizer

    @bucketizer.setter
    def bucketizer(self, value):
        self._services.bucketizer = value

    @property
    def event_aggregator(self):
        """Public accessor for the event aggregator (used by Scheduler for media fetch)."""
        return self._services.event_aggregator

    # -- event emission -------------------------------------------------------

    async def _emit(self, event: dict[str, Any]) -> None:
        """Publish a pipeline event; errors are dead-lettered (rule 15).

        Publisher failure must not interrupt execution; this is a side-channel.
        One increment logged per failed publish for observability (rule 13).
        """
        if self._event_publisher is None:
            return
        try:
            await self._event_publisher(event)
        except Exception:  # noqa: BLE001
            logger.warning("pipeline_event_publish_failed", event_type=event.get("event_type"))

    def _next_seq(self) -> int:
        self._event_sequence += 1
        return self._event_sequence

    # -- public API -----------------------------------------------------------

    async def fire_event(
        self,
        *,
        source: str,
        kind: str,
        payload: dict[str, Any],
    ) -> None:
        """Lightweight event dispatch for CTS subscribers and the bucketizer.

        This satisfies the ``PipelineExecutor`` protocol from
        ``backend.services.cts._types``. It is called by
        ``TrackingEventSubscriber``, ``IdentityRevisionSubscriber``,
        ``DementiaSignalSubscriber``, and ``CtsEventBucketizer``.

        Unlike :meth:`execute`, this method does not require a Rule or a
        database session — it is a fire-and-forget signal that the
        RulesEngine can optionally consume when the ``cts_window`` trigger
        type is activated.
        """
        logger.info(
            "pipeline_fire_event",
            source=source,
            kind=kind,
            payload_keys=sorted(payload.keys()) if payload else [],
        )
        if self._rules_engine is None:
            return

        event = {"kind": kind, "payload": payload}
        db = self._services.db_factory()
        try:
            rules = self._rules_engine.get_matching_rules_for_event(event, kind, db)
        finally:
            db.close()

        if not rules:
            return

        trigger = TriggerContext(trigger_type=kind)
        for rule in rules:
            rule_db = self._services.db_factory()
            try:
                await self.execute(rule, trigger, rule_db)
            except Exception:
                logger.exception("fire_event_rule_execute_error", rule=rule.name, kind=kind)
            finally:
                rule_db.close()

    async def execute(
        self,
        rule: Rule,
        trigger: TriggerContext,
        db: Session,
    ) -> WorkflowExecution:
        """Run a rule's pipeline from the first step.

        Applies ``rule.execution_timeout_minutes`` as a hard wall-clock limit
        over the active execution (waits do not count against the limit because
        the coroutine is not running during a wait).
        """
        logger.info(
            "pipeline_execute_start",
            rule=rule.name,
            rule_id=rule.id,
            trigger_type=trigger.trigger_type,
            sensor_id=trigger.sensor_id,
        )
        steps = sorted(
            [s for s in rule.steps if s.enabled],
            key=lambda s: s.order,
        )
        edges = db.query(PipelineEdge).filter(PipelineEdge.rule_id == rule.id).all()
        adjacency, entry_step_ids = _prepare_execution_graph(steps, edges)

        # Create event log
        event_log = EventLog(
            rule_id=rule.id,
            rule_name=rule.name,
            sensor_id=trigger.sensor_id,
            room_name=trigger.room_name,
            trigger_type=trigger.trigger_type,
            media_paths_json=trigger.media_paths,
            status="processing",
        )
        db.add(event_log)
        db.flush()

        local_tz = ZoneInfo(settings.as_str("app.timezone"))
        now_local = datetime.now(local_tz)
        now_utc = datetime.now(UTC)

        pipeline_data: dict = build_initial_pipeline_data(
            trigger_type=trigger.trigger_type,
            sensor_id=trigger.sensor_id,
            room_name=trigger.room_name,
            media_paths=trigger.media_paths,
            media_type=trigger.media_type,
            webhook_payload=trigger.webhook_payload,
            now_utc=now_utc,
            now_local=now_local,
            timezone_name=str(local_tz),
        )
        graph_snapshot = build_graph_snapshot(steps, edges, _output_ports_for_step_type)
        pipeline_data["_graph"] = graph_snapshot

        execution = WorkflowExecution(
            rule_id=rule.id,
            event_log_id=event_log.id,
            status="running",
            pipeline_data_json=pipeline_data,
        )
        db.add(execution)
        db.flush()

        event_log.workflow_execution_id = execution.id
        db.commit()
        db.refresh(execution)

        # Emit pipeline_started event.
        rule_name_str = rule.name
        await self._emit(
            PipelineStartedEvent(
                execution_id=execution.id,
                rule_id=rule.id,
                rule_name=rule_name_str,
                status="running",
                started_at=now_utc,
                sequence=self._next_seq(),
                steps=[
                    StepNodeRef(
                        id=str(step["id"]),
                        label=step["label"],
                        step_type=step["step_type"],
                        enabled=True,
                    )
                    for step in graph_snapshot["steps"]
                ],
                edges=[
                    EdgeRef(
                        source=str(edge["source_step_id"]),
                        source_handle=edge["source_port"],
                        target=str(edge["target_step_id"]),
                        target_handle=edge["target_port"],
                    )
                    for edge in graph_snapshot["edges"]
                ],
            ).model_dump(mode="json")
        )

        if not steps:
            completed_at = datetime.now(UTC)
            execution.status = "completed"
            execution.completed_at = completed_at
            _mark_pipeline_completed(execution, completed_at)
            event_log.status = "completed"
            db.commit()
            logger.info("pipeline_no_steps", rule=rule.name)
            return execution

        timeout_seconds: float | None = (
            rule.execution_timeout_minutes * 60 if rule.execution_timeout_minutes > 0 else None
        )

        try:
            return await asyncio.wait_for(
                self._run_steps(execution, steps, trigger, db, adjacency, entry_step_ids),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            return self._handle_timeout(rule, execution, db)

    async def resume(self, execution_id: int, db: Session) -> WorkflowExecution:
        """Resume a waiting workflow execution from its current step.

        Uses pessimistic locking (SELECT FOR UPDATE) to ensure exclusive access
        during the critical status transition from 'waiting' to 'running'. This
        prevents race conditions where multiple resume attempts could occur
        simultaneously (e.g., manual resume + scheduled resume).

        For interactive_prompt steps, loads the recorded response and merges it
        into pipeline_data before continuing to the next step.
        """
        # CRITICAL SECTION: Acquire row-level lock for status transition
        execution = (
            db.query(WorkflowExecution)
            .filter(WorkflowExecution.id == execution_id)
            .with_for_update()
            .first()
        )
        if not execution:
            raise ValueError(f"WorkflowExecution {execution_id} not found")

        if execution.status != "waiting":
            logger.warning(
                "resume_non_waiting",
                execution_id=execution_id,
                status=execution.status,
            )
            return execution

        rule = execution.rule
        steps = sorted(
            [s for s in rule.steps if s.enabled],
            key=lambda s: s.order,
        )
        edges = db.query(PipelineEdge).filter(PipelineEdge.rule_id == rule.id).all()
        adjacency, _entry_step_ids = _prepare_execution_graph(steps, edges)

        current_step: PipelineStep | None = None
        if execution.current_step_id:
            for s in steps:
                if s.id == execution.current_step_id:
                    current_step = s
                    break

        # For interactive_prompt steps: merge the response into pipeline_data
        # before advancing. The executor is the only writer of pipeline_data_json.
        if current_step and current_step.step_type == "interactive_prompt":
            merged = self._merge_interactive_response(execution, current_step, db)
            if not merged:
                # Response not yet available; keep waiting
                logger.info(
                    "resume_interactive_no_response_yet",
                    execution_id=execution_id,
                    step_id=current_step.id,
                )
                return execution

        if current_step is not None:
            all_step_ids = {s.id for s in steps}
            descendant_ids = find_descendants(current_step.id, all_step_ids, edges)
            steps = [s for s in steps if s.id in descendant_ids]
            remaining_step_ids = {s.id for s in steps}
            # Resume from every step immediately downstream of the resumed step,
            # across all of its output ports (a port may now fan out to several).
            entry_ids_for_resume = [
                target_id
                for targets in adjacency.get(current_step.id, {}).values()
                for target_id in targets
                if target_id in remaining_step_ids
            ]
        else:
            entry_ids_for_resume = find_entry_step_ids({s.id for s in steps}, edges)

        execution.status = "running"
        execution.resume_at = None
        db.commit()

        trigger_data = (execution.pipeline_data_json or {}).get("trigger", {})
        trigger = TriggerContext(
            trigger_type="resume",
            sensor_id=trigger_data.get("sensor_id"),
            room_name=trigger_data.get("room_name"),
            media_paths=trigger_data.get("media_paths", []),
            media_type=trigger_data.get("media_type", "image"),
        )

        timeout_seconds: float | None = (
            rule.execution_timeout_minutes * 60 if rule.execution_timeout_minutes > 0 else None
        )

        try:
            return await asyncio.wait_for(
                self._run_steps(
                    execution,
                    steps,
                    trigger,
                    db,
                    adjacency,
                    entry_ids_for_resume,
                ),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            return self._handle_timeout(rule, execution, db)

    def _merge_interactive_response(
        self,
        execution: WorkflowExecution,
        step: PipelineStep,
        db: Session,
    ) -> bool:
        """Load the InteractiveResponse for *step* and merge it into pipeline_data.

        Returns True if a response was found and merged, False otherwise.
        The caller holds the row lock so this is safe to commit.
        """
        from backend.models.interactive_response import InteractiveResponse
        from backend.services.pipeline_data_manager import apply_interactive_response

        response = (
            db.query(InteractiveResponse)
            .filter(
                InteractiveResponse.execution_id == execution.id,
                InteractiveResponse.step_id == step.id,
            )
            .first()
        )
        if response is None:
            return False

        config = step.config_json or {}
        output_key = config.get("output_key", "interactive_response")
        auto_escalate = config.get("auto_escalate", False)

        response_payload = {
            "channel": response.channel,
            "action": response.action,
            "timestamp": response.timestamp.isoformat(),
            "raw_response": response.raw_response_json or {},
        }

        pipeline_data = execution.pipeline_data_json
        if pipeline_data is None:
            execution.pipeline_data_json = {}
            pipeline_data = execution.pipeline_data_json

        apply_interactive_response(
            pipeline_data,
            step_id=step.id,
            step_type=step.step_type,
            label=step.label,
            output_key=output_key,
            response_payload=response_payload,
            auto_escalate=auto_escalate,
            channel=response.channel,
            action=response.action,
        )
        flag_modified(execution, "pipeline_data_json")
        db.commit()
        return True

    # -- step execution -------------------------------------------------------

    async def _run_steps(
        self,
        execution: WorkflowExecution,
        steps: list[PipelineStep],
        trigger: TriggerContext,
        db: Session,
        adjacency: dict[int, dict[str, list[int]]],
        entry_step_ids: list[int],
    ) -> WorkflowExecution:
        """Traverse the pipeline DAG, handling timing, waits, and early exit.

        Traversal is **in-degree gated**: a step runs only once every incoming
        edge has been resolved by its source completing. Each outgoing edge is
        either *live* (its source activated that port) or *dead* (the source took
        another branch, e.g. a ``condition`` emitting only ``true``). A node with
        at least one live incoming edge executes; a node whose incoming edges are
        all dead is skipped, and that skip propagates to its descendants. This
        makes fan-out (one port to many targets) and fan-in/joins (a node waits
        for all parents, then runs once) correct for arbitrary DAGs, not just the
        linear/symmetric cases the previous breadth-first walk happened to handle.

        ``execution.pipeline_data_json`` is wrapped by
        :class:`sqlalchemy.ext.mutable.MutableDict` (see the column definition
        on :class:`WorkflowExecution`). All writes in this method go through
        that tracked reference so SQLAlchemy flushes the updated JSON on every
        ``db.commit()``. Do not rebind a local plain-dict copy: mutations to a
        detached copy would not be flagged dirty, and because the session
        factory runs with ``expire_on_commit=False`` the row would silently
        drift out of sync with in-memory state.

        Nested mutations such as ``pipeline_data["_pipeline"]["completed_at"]``
        are invisible to ``MutableDict``; call :func:`_mark_pipeline_completed`
        (which uses :func:`flag_modified`) for those.
        """
        pipeline_data = execution.pipeline_data_json
        if pipeline_data is None:
            execution.pipeline_data_json = {}
            pipeline_data = execution.pipeline_data_json

        # Preserve timings across resume cycles
        step_timings: list = list(pipeline_data.get("_step_timings", []))

        step_by_id = {s.id: s for s in steps}
        step_ids_set = set(step_by_id)

        # In-degree counts only edges whose source is in the run set. On resume
        # the run set is the descendant subset, so edges from already-executed
        # ancestors are treated as pre-resolved (not counted here).
        _active_step: PipelineStep | None = None
        _active_step_started_at: datetime | None = None
        should_stop_traversal = False
        resolved_nodes: set[int] = set()

        async def execute_node(node_id: int) -> NodeOutcome:
            nonlocal _active_step, _active_step_started_at, should_stop_traversal, pipeline_data
            resolved_nodes.add(node_id)

            step = step_by_id.get(node_id)
            if step is None:
                logger.warning(
                    "dag_step_not_found",
                    rule=execution.rule.name,
                    step_id=node_id,
                )
                return NodeOutcome(active_ports=frozenset())

            execution.current_step_id = step.id
            db.commit()

            # Cooperative cancellation: check if execution was cancelled
            db.refresh(execution)
            pipeline_data = execution.pipeline_data_json  # re-bind after refresh
            if pipeline_data is None:
                execution.pipeline_data_json = {}
                pipeline_data = execution.pipeline_data_json
            if execution.status == "cancelled":
                step_timings.append(
                    _make_step_timing(
                        step,
                        datetime.now(UTC),
                        datetime.now(UTC),
                        success=False,
                        error="Execution cancelled",
                        cancellation_observed=True,
                    )
                )
                pipeline_data["_step_timings"] = step_timings
                db.commit()
                logger.info(
                    "step_cancelled",
                    rule=execution.rule.name,
                    step_label=step.label,
                )
                await self._emit(
                    PipelineCancelledEvent(
                        execution_id=execution.id,
                        rule_id=execution.rule_id,
                        rule_name=execution.rule.name,
                        status="cancelled",
                        finished_at=datetime.now(UTC),
                        sequence=self._next_seq(),
                    ).model_dump(mode="json")
                )
                should_stop_traversal = True
                return NodeOutcome(active_ports=frozenset(), stop=True)

            logger.info(
                "step_executing",
                rule=execution.rule.name,
                step_type=step.step_type,
                step_label=step.label,
                order=step.order,
            )

            _active_step = step
            _active_step_started_at = datetime.now(UTC)

            # Emit step_started (one event per transition, one increment per code path).
            await self._emit(
                StepStartedEvent(
                    execution_id=execution.id,
                    rule_id=execution.rule_id,
                    rule_name=execution.rule.name,
                    step_id=str(step.id),
                    step_name=step.label or step.step_type,
                    step_type=step.step_type,
                    status="running",
                    started_at=_active_step_started_at,
                    sequence=self._next_seq(),
                ).model_dump(mode="json")
            )

            # Per-step timeout (coarse safety net for stuck LLM calls)
            try:
                result = await asyncio.wait_for(
                    self._execute_step(step, execution, pipeline_data, trigger),
                    timeout=_PER_STEP_TIMEOUT,
                )
            except TimeoutError:
                result = StepResult(
                    success=False,
                    data={"error": f"Step timed out after {_PER_STEP_TIMEOUT:.0f}s"},
                )

            step_completed_at = datetime.now(UTC)
            step_started_at = _active_step_started_at
            assert step_started_at is not None
            output_port = result.output_ports[0] if result.output_ports else "main"
            step_timings.append(
                _make_step_timing(
                    step,
                    step_started_at,
                    step_completed_at,
                    result.success,
                    error=result.data.get("error") if not result.success else None,
                    output_port=output_port,
                )
            )
            # Emit step_completed (one event per transition, one increment per code path).
            elapsed_ms = int((step_completed_at - step_started_at).total_seconds() * 1000)
            await self._emit(
                StepCompletedEvent(
                    execution_id=execution.id,
                    rule_id=execution.rule_id,
                    rule_name=execution.rule.name,
                    step_id=str(step.id),
                    step_name=step.label or step.step_type,
                    step_type=step.step_type,
                    status="succeeded" if result.success else "failed",
                    started_at=step_started_at,
                    finished_at=step_completed_at,
                    error_code=(result.data.get("error") if not result.success else None),
                    output_port=output_port,
                    elapsed_ms=elapsed_ms,
                    sequence=self._next_seq(),
                ).model_dump(mode="json")
            )
            # Signal to the except-block that this step's timing is already saved
            _active_step_started_at = None

            # Merge step output into the tracked dict via the canonical helper.
            # apply_step_result writes steps.<label>.outputs and promotes
            # pipeline control flags (_cooloff_triggered) to the top level.
            apply_step_result(
                pipeline_data,
                step_id=step.id,
                step_type=step.step_type,
                label=step.label,
                result_data=result.data,
            )

            pipeline_data["_step_timings"] = step_timings
            db.commit()

            # Handle wait
            if result.wait_until:
                # Pausing serializes the whole execution, and resume() only
                # rebuilds work downstream of the waiting step. If any step
                # in a parallel branch (neither already processed nor
                # reachable from here) is still pending, resuming would
                # silently drop it. Fail loudly instead of losing a branch.
                # Resuming all branches across a wait is a future enhancement.
                abandoned = (
                    step_ids_set
                    - resolved_nodes
                    - _descendants_via_adjacency(step.id, adjacency, step_ids_set)
                )
                if abandoned:
                    logger.error(
                        "pipeline_wait_parallel_branch_unsupported",
                        execution_id=execution.id,
                        step_label=step.label or step.step_type,
                        abandoned_step_ids=sorted(abandoned),
                    )
                    raise ValidationError(
                        f"Step '{step.label or step.step_type}' pauses (wait) while "
                        f"{len(abandoned)} step(s) remain in a parallel branch. "
                        "wait/interactive_prompt steps are not yet supported alongside "
                        "fan-out branches; restructure the pipeline so the wait is not "
                        "parallel to other steps."
                    )
                execution.status = "waiting"
                execution.resume_at = result.wait_until
                # Record which step we are waiting on so resume() can
                # load the interactive response if needed.
                execution.current_step_id = step.id
                db.commit()
                if self._services.scheduler and step.step_type != "interactive_prompt":
                    self._services.scheduler.schedule_workflow_resume(
                        execution.id, result.wait_until
                    )
                logger.info(
                    "pipeline_waiting",
                    execution_id=execution.id,
                    resume_at=result.wait_until.isoformat(),
                )
                await self._emit(
                    PipelineWaitingEvent(
                        execution_id=execution.id,
                        rule_id=execution.rule_id,
                        rule_name=execution.rule.name,
                        status="waiting",
                        sequence=self._next_seq(),
                    ).model_dump(mode="json")
                )
                should_stop_traversal = True
                return NodeOutcome(active_ports=frozenset(), stop=True)

            # Handle early exit.
            if not result.should_continue:
                completed_at = datetime.now(UTC)
                if result.success:
                    execution.status = "completed"
                    event_log_status = "ignored"
                else:
                    execution.status = "failed"
                    event_log_status = "failed"
                execution.completed_at = completed_at
                _mark_pipeline_completed(execution, completed_at)

                skip_reason = result.data.get("skip_reason")

                event_log = db.query(EventLog).filter(EventLog.id == execution.event_log_id).first()
                if event_log:
                    event_log.status = event_log_status
                    event_log.pipeline_data_json = copy_pipeline_snapshot(pipeline_data)
                db.commit()
                logger.info(
                    "pipeline_early_exit",
                    rule=execution.rule.name,
                    step=step.label or step.step_type,
                    event_log_status=event_log_status,
                    skip_reason=skip_reason,
                )
                should_stop_traversal = True
                return NodeOutcome(active_ports=frozenset(), stop=True)

            return NodeOutcome(active_ports=frozenset(result.output_ports))

        async def on_skip(node_id: int) -> None:
            resolved_nodes.add(node_id)
            step = step_by_id.get(node_id)
            if step is not None:
                logger.info(
                    "step_skipped_dead_branch",
                    rule=execution.rule.name,
                    step_type=step.step_type,
                    step_label=step.label,
                )

        try:
            await traverse_dag(
                node_ids=step_ids_set,
                adjacency=adjacency,
                entry_ids=entry_step_ids,
                execute_node=execute_node,
                on_skip=on_skip,
            )

            if should_stop_traversal:
                return execution

            # All steps completed
            completed_at = datetime.now(UTC)
            execution.status = "completed"
            execution.completed_at = completed_at
            pipeline_data["_step_timings"] = step_timings
            _mark_pipeline_completed(execution, completed_at)

            event_log = db.query(EventLog).filter(EventLog.id == execution.event_log_id).first()
            if event_log:
                if pipeline_data.get("_cooloff_triggered", False):
                    event_log.status = "completed"
                else:
                    event_log.status = "ignored"
                event_log.pipeline_data_json = copy_pipeline_snapshot(pipeline_data)
            db.commit()

            logger.info(
                "pipeline_completed",
                rule=execution.rule.name,
                cooloff_triggered=pipeline_data.get("_cooloff_triggered", False),
            )
            await self._emit(
                PipelineCompletedEvent(
                    execution_id=execution.id,
                    rule_id=execution.rule_id,
                    rule_name=execution.rule.name,
                    status="completed",
                    finished_at=completed_at,
                    sequence=self._next_seq(),
                ).model_dump(mode="json")
            )
            return execution

        except Exception as e:
            import contextlib

            # Rollback any failed transaction before attempting cleanup writes.
            with contextlib.suppress(Exception):
                db.rollback()

            # Re-bind after rollback: the execution's tracked reference may have
            # been replaced, so the local ``pipeline_data`` variable is stale.
            pipeline_data = execution.pipeline_data_json
            if pipeline_data is None:
                execution.pipeline_data_json = {}
                pipeline_data = execution.pipeline_data_json

            completed_at = datetime.now(UTC)

            # Record timing for the step that raised, if not already saved
            if _active_step is not None and _active_step_started_at is not None:
                step_timings.append(
                    _make_step_timing(
                        _active_step,
                        _active_step_started_at,
                        completed_at,
                        success=False,
                        error=str(e),
                    )
                )

            logger.error(
                "pipeline_error",
                rule=execution.rule.name,
                error=str(e),
                exc_info=True,
            )
            pipeline_data["_step_timings"] = step_timings
            pipeline_data["error"] = str(e)
            _mark_pipeline_completed(execution, completed_at)

            execution.status = "failed"
            execution.completed_at = completed_at
            execution.error = str(e)

            event_log = db.query(EventLog).filter(EventLog.id == execution.event_log_id).first()
            if event_log:
                event_log.status = "failed"
                event_log.pipeline_data_json = copy_pipeline_snapshot(pipeline_data)
            db.commit()
            await self._emit(
                PipelineFailedEvent(
                    execution_id=execution.id,
                    rule_id=execution.rule_id,
                    rule_name=execution.rule.name,
                    status="failed",
                    error_code=str(e),
                    finished_at=completed_at,
                    sequence=self._next_seq(),
                ).model_dump(mode="json")
            )
            return execution

    async def _execute_step(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
    ) -> StepResult:
        """Dispatch to the appropriate step handler via the StepRegistry."""
        handler = StepRegistry.get(step.step_type)
        if not handler:
            logger.warning("unknown_step_type", step_type=step.step_type)
            return StepResult(success=False, should_continue=False)

        return await handler.execute(step, execution, pipeline_data, trigger, self._services)

    # -- helpers --------------------------------------------------------------

    def _handle_timeout(
        self,
        rule: Rule,
        execution: WorkflowExecution,
        db: Session,
    ) -> WorkflowExecution:
        """Mark the execution as failed due to timeout and persist the state.

        Uses pessimistic locking (SELECT FOR UPDATE) to ensure exclusive access
        when transitioning to 'failed' status.
        """
        completed_at = datetime.now(UTC)
        error_msg = (
            f"Pipeline timed out after {rule.execution_timeout_minutes} minute"
            f"{'s' if rule.execution_timeout_minutes != 1 else ''}"
        )

        # CRITICAL SECTION: Acquire row-level lock for timeout handling
        db.rollback()  # Discard any uncommitted changes from cancelled coroutine
        execution = (
            db.query(WorkflowExecution)
            .filter(WorkflowExecution.id == execution.id)
            .with_for_update()
            .one()
        )

        pipeline_data = execution.pipeline_data_json
        if pipeline_data is None:
            execution.pipeline_data_json = {}
            pipeline_data = execution.pipeline_data_json

        pipeline_data["error"] = error_msg
        _mark_pipeline_completed(execution, completed_at)

        execution.status = "failed"
        execution.completed_at = completed_at
        execution.error = error_msg

        event_log = db.query(EventLog).filter(EventLog.id == execution.event_log_id).first()
        if event_log:
            event_log.status = "failed"
        db.commit()

        logger.error(
            "pipeline_timeout",
            rule=rule.name,
            execution_id=execution.id,
            timeout_minutes=rule.execution_timeout_minutes,
        )
        return execution


def _make_step_timing(
    step: PipelineStep,
    started_at: datetime,
    completed_at: datetime,
    success: bool,
    error: str | None = None,
    cancellation_observed: bool = False,
    output_port: str = "main",
) -> dict:
    """Build a timing entry dict for a single pipeline step."""
    entry: dict = {
        "step_id": step.id,
        "step_type": step.step_type,
        "label": step.label,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "elapsed_seconds": round((completed_at - started_at).total_seconds(), 3),
        "success": success,
        "output_port": output_port,
        "logs": [],
    }
    if error is not None:
        entry["error"] = error
    if cancellation_observed:
        entry["cancellation_observed"] = True
    return entry


def _prepare_execution_graph(
    steps: list[PipelineStep],
    edges: list[PipelineEdge],
) -> tuple[dict[int, dict[str, list[int]]], list[int]]:
    """Validate enabled-step topology and return routing maps for execution."""
    if not steps:
        return {}, []

    errors = validate_graph(
        {step.id for step in steps},
        edges,
        _collect_step_output_ports(steps),
    )
    if errors:
        raise ValidationError("; ".join(errors))

    return build_adjacency(edges), find_entry_step_ids({step.id for step in steps}, edges)


def _collect_step_output_ports(steps: list[PipelineStep]) -> dict[int, tuple[str, ...]]:
    StepRegistry.discover()
    output_ports: dict[int, tuple[str, ...]] = {}
    for step in steps:
        output_ports[step.id] = _output_ports_for_step_type(step.step_type)
    return output_ports


def _output_ports_for_step_type(step_type: str) -> tuple[str, ...]:
    StepRegistry.discover()
    handler = StepRegistry.get(step_type)
    return handler.metadata().output_ports if handler else ("main",)


def _descendants_via_adjacency(
    start_step_id: int,
    adjacency: dict[int, dict[str, list[int]]],
    allowed: set[int],
) -> set[int]:
    """Return steps in *allowed* reachable from *start_step_id* (excluding it)."""
    seen: set[int] = set()
    dq: deque[int] = deque([start_step_id])
    while dq:
        cur = dq.popleft()
        for targets in adjacency.get(cur, {}).values():
            for target_id in targets:
                if target_id in allowed and target_id not in seen:
                    seen.add(target_id)
                    dq.append(target_id)
    return seen


_PER_STEP_TIMEOUT = 60.0  # seconds; coarse safety net for stuck LLM calls


def _mark_pipeline_completed(execution: WorkflowExecution, completed_at: datetime) -> None:
    """Stamp ``pipeline_data_json['_pipeline']['completed_at']`` and mark dirty.

    This mutates a nested dict inside the ``MutableDict``-wrapped JSON
    column. ``MutableDict`` only tracks top-level ``__setitem__`` / ``update``
    calls, so nested writes must be reported to SQLAlchemy explicitly via
    :func:`flag_modified` or the next flush will miss the change.
    """
    pipeline_data = execution.pipeline_data_json
    if pipeline_data is None:
        return
    block = pipeline_data.setdefault("_pipeline", {})
    block["completed_at"] = completed_at.isoformat()
    flag_modified(execution, "pipeline_data_json")


async def _update_pipeline_data_with_retry(
    db: Session,
    execution_id: int,
    update_fn: Callable[[dict], None],
) -> None:
    """Update pipeline_data_json with optimistic locking retry.

    Implements exponential backoff retry on StaleDataError to handle
    concurrent updates to WorkflowExecution.pipeline_data_json.

    Args:
        db: Database session
        execution_id: ID of the WorkflowExecution to update
        update_fn: Callable that receives pipeline_data_json dict and mutates it

    Raises:
        StaleDataError: If all retry attempts are exhausted
    """
    for attempt in range(MAX_RETRIES):
        try:
            execution = db.query(WorkflowExecution).filter_by(id=execution_id).one()
            update_fn(execution.pipeline_data_json)
            flag_modified(execution, "pipeline_data_json")
            db.commit()
            return
        except StaleDataError:
            if attempt == MAX_RETRIES - 1:
                logger.error(
                    "optimistic_lock_exhausted",
                    execution_id=execution_id,
                    attempts=MAX_RETRIES,
                )
                raise
            delay = BASE_DELAY * (2**attempt)  # Exponential backoff
            logger.warning(
                "optimistic_lock_conflict",
                execution_id=execution_id,
                attempt=attempt + 1,
                retry_delay_seconds=delay,
            )
            await asyncio.sleep(delay)
            db.rollback()
