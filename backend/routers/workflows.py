"""Workflow execution endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.models.pipeline import WorkflowExecution
from backend.models.rule import Rule
from backend.schemas.workflow import (
    ExecutionDetailOut,
    RerunRequest,
    StepTimelineEntry,
    WorkflowExecutionListOut,
    WorkflowExecutionOut,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowExecutionListOut])
def list_executions(
    rule_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("caregiver")),
):
    """List workflow executions with optional filters."""
    query = db.query(WorkflowExecution).join(Rule)
    if rule_id is not None:
        query = query.filter(WorkflowExecution.rule_id == rule_id)
    if status:
        query = query.filter(WorkflowExecution.status == status)

    executions = query.order_by(WorkflowExecution.started_at.desc()).limit(limit).all()

    # Attach rule_name for the response
    results = []
    for ex in executions:
        data = WorkflowExecutionListOut.model_validate(ex)
        data.rule_name = ex.rule.name if ex.rule else None
        results.append(data)
    return results


@router.get("/{execution_id}", response_model=WorkflowExecutionOut)
def get_execution(
    execution_id: int,
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("caregiver")),
):
    """Get detailed workflow execution with pipeline data."""
    execution = db.query(WorkflowExecution).get(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Workflow execution not found")

    result = WorkflowExecutionOut.model_validate(execution)
    result.rule_name = execution.rule.name if execution.rule else None
    return result


@router.post("/{execution_id}/cancel", status_code=200)
async def cancel_execution(
    execution_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Cancel a running or waiting workflow execution."""
    execution = (
        db.query(WorkflowExecution)
        .filter(WorkflowExecution.id == execution_id)
        .with_for_update()
        .first()
    )
    if not execution:
        raise HTTPException(status_code=404, detail="Workflow execution not found")
    if execution.status not in ("running", "waiting"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel execution in '{execution.status}' state",
        )

    execution.status = "cancelled"
    execution.resume_at = None
    execution.error = f"Cancelled by {_auth.name}"

    # Remove scheduled resume job if one exists
    import contextlib
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        with contextlib.suppress(Exception):
            scheduler.remove_job(f"resume_{execution_id}")

    db.commit()
    logger.info("execution_cancelled", execution_id=execution_id, by=_auth.name)

    return {"id": execution.id, "status": "cancelled"}


@router.get("/{execution_id}/detail", response_model=ExecutionDetailOut)
def get_execution_detail(
    execution_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("caregiver")),
):
    """Return a rich, UI-ready execution detail view model."""
    from backend.steps import StepRegistry

    execution = (
        db.query(WorkflowExecution)
        .options(joinedload(WorkflowExecution.rule))
        .filter(WorkflowExecution.id == execution_id)
        .first()
    )
    if not execution:
        raise HTTPException(status_code=404, detail="Workflow execution not found")

    pd = execution.pipeline_data_json or {}
    trigger_data = pd.get("trigger", {})
    trigger_type = trigger_data.get("type", "unknown")
    trigger_summary = _build_trigger_summary(trigger_type, trigger_data)

    timeline: list[StepTimelineEntry] = []
    for timing in pd.get("_step_timings", []):
        step_type = timing.get("step_type", "")
        label = timing.get("label", "")
        meta = None
        handler = StepRegistry.get(step_type)
        if handler:
            meta = handler.metadata()

        timeline.append(
            StepTimelineEntry(
                label=label,
                step_type=step_type,
                icon=meta.icon if meta else "mdi-cog",
                category=meta.category if meta else "flow",
                status="success" if timing.get("success") else "failed",
                elapsed_seconds=timing.get("elapsed_seconds"),
                resolved_config=timing.get("resolved_config"),
                outputs=pd.get("steps", {}).get(label, {}).get("outputs"),
                logs=timing.get("logs", []),
                error=timing.get("error"),
                cancellation_observed=timing.get("cancellation_observed", False),
            )
        )

    return ExecutionDetailOut(
        id=execution.id,
        rule_id=execution.rule_id,
        status=execution.status,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        rule_name=execution.rule.name if execution.rule else "Unknown",
        trigger_type=trigger_type,
        trigger_summary=trigger_summary,
        timeline=timeline,
        cooloff_triggered=pd.get("_cooloff_triggered", False),
        error=execution.error,
        can_cancel=execution.status in ("running", "waiting"),
        can_rerun=True,
    )


@router.post("/{execution_id}/rerun", status_code=202)
async def rerun_execution(
    execution_id: int,
    payload: RerunRequest,
    request: Request,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Rerun a workflow execution from the beginning (v1).

    Copies the original TriggerContext and re-executes all enabled steps.
    """
    from backend.steps.base import TriggerContext

    execution = (
        db.query(WorkflowExecution)
        .options(joinedload(WorkflowExecution.rule).joinedload(Rule.steps))
        .filter(WorkflowExecution.id == execution_id)
        .first()
    )
    if not execution:
        raise HTTPException(status_code=404, detail="Workflow execution not found")

    rule = execution.rule
    if not rule or not rule.enabled:
        raise HTTPException(status_code=400, detail="Rule not found or disabled")

    pd = execution.pipeline_data_json or {}
    trigger_data = pd.get("trigger", {})

    trigger = TriggerContext(
        trigger_type=trigger_data.get("type", "manual"),
        sensor_id=trigger_data.get("sensor_id"),
        room_name=trigger_data.get("room_name"),
        media_paths=trigger_data.get("media_paths", []),
        media_type=trigger_data.get("media_type", "image"),
    )

    pipeline_executor = request.app.state.pipeline_executor
    new_execution = await pipeline_executor.execute(rule, trigger, db)

    logger.info(
        "execution_rerun",
        original_execution_id=execution_id,
        new_execution_id=new_execution.id,
        rule_name=rule.name,
    )

    return {
        "execution_id": new_execution.id,
        "status": new_execution.status,
    }


def _build_trigger_summary(trigger_type: str, trigger_data: dict) -> str:
    """Build a human-readable trigger summary."""
    if trigger_type == "cron":
        cron_name = trigger_data.get("cron_trigger_name", "")
        return f"Cron: {cron_name}" if cron_name else "Cron schedule"
    if trigger_type == "sensor_event":
        sensor = trigger_data.get("sensor_id", "unknown")
        room = trigger_data.get("room_name", "")
        return f"Sensor: {sensor}" + (f" ({room})" if room else "")
    if trigger_type == "manual":
        return "Manual trigger"
    if trigger_type == "webhook":
        return "Webhook"
    if trigger_type == "telegram":
        return "Telegram command"
    if trigger_type == "occupancy_duration":
        return "Occupancy duration"
    if trigger_type == "resume":
        return "Resume after wait"
    return trigger_type
