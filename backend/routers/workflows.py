"""Workflow execution endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.auth import require_permission
from backend.core.database import get_db
from backend.models.pipeline import WorkflowExecution
from backend.models.rule import Rule
from backend.schemas.workflow import WorkflowExecutionListOut, WorkflowExecutionOut

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
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("admin")),
):
    """Cancel a running or waiting workflow execution."""
    execution = db.query(WorkflowExecution).get(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Workflow execution not found")
    if execution.status not in ("running", "waiting"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel execution in '{execution.status}' state",
        )

    execution.status = "cancelled"
    execution.resume_at = None
    db.commit()

    return {"id": execution.id, "status": "cancelled"}
