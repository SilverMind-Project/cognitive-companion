"""Rule and pipeline step CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, joinedload

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.exceptions import ConflictError, NotFoundError
from backend.models.pipeline import PipelineStep
from backend.models.rule import Rule, RuleContext, RuleDependency
from backend.schemas.rule import (
    ContextCreate,
    DependencyCreate,
    PipelineStepCreate,
    PipelineStepOut,
    PipelineStepReorder,
    PipelineStepUpdate,
    RuleContextOut,
    RuleCreate,
    RuleDependencyOut,
    RuleListOut,
    RuleOut,
    RuleUpdate,
)

router = APIRouter(prefix="/rules", tags=["rules"])


# ---------------------------------------------------------------------------
# Rules CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[RuleListOut])
def list_rules(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    return db.query(Rule).order_by(Rule.name).all()


@router.post("", response_model=RuleOut, status_code=201)
def create_rule(
    payload: RuleCreate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    existing = db.query(Rule).filter(Rule.name == payload.name).first()
    if existing:
        raise ConflictError(f"Rule '{payload.name}' already exists")
    rule = Rule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/{rule_id}", response_model=RuleOut)
def get_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    rule = (
        db.query(Rule)
        .options(
            joinedload(Rule.steps),
            joinedload(Rule.contexts),
            joinedload(Rule.dependencies),
        )
        .filter(Rule.id == rule_id)
        .first()
    )
    if not rule:
        raise NotFoundError("Rule", rule_id)
    return rule


@router.put("/{rule_id}", response_model=RuleOut)
def update_rule(
    rule_id: int,
    payload: RuleUpdate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise NotFoundError("Rule", rule_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    from backend.models.event import EventLog
    from backend.models.pipeline import WorkflowExecution

    rule = db.get(Rule, rule_id)
    if not rule:
        raise NotFoundError("Rule", rule_id)

    # FK dependency order:
    #   event_logs.workflow_execution_id → workflow_executions.id
    #   event_logs.rule_id              → rules.id
    #   workflow_executions.rule_id     → rules.id
    #   pipeline_steps (self-ref)       next_step_on_true/false → pipeline_steps.id

    exec_ids = [
        row[0]
        for row in db.query(WorkflowExecution.id).filter(WorkflowExecution.rule_id == rule_id).all()
    ]
    if exec_ids:
        db.query(EventLog).filter(EventLog.workflow_execution_id.in_(exec_ids)).update(
            {"workflow_execution_id": None}, synchronize_session=False
        )

    db.query(EventLog).filter(EventLog.rule_id == rule_id).update(
        {"rule_id": None}, synchronize_session=False
    )

    db.query(WorkflowExecution).filter(WorkflowExecution.rule_id == rule_id).delete(
        synchronize_session=False
    )

    # Clear self-referential step branch FKs so cascade delete can proceed
    db.query(PipelineStep).filter(PipelineStep.rule_id == rule_id).update(
        {"next_step_on_true": None, "next_step_on_false": None},
        synchronize_session=False,
    )

    db.delete(rule)
    db.commit()


# ---------------------------------------------------------------------------
# Pipeline Steps
# ---------------------------------------------------------------------------


@router.get("/{rule_id}/steps", response_model=list[PipelineStepOut])
def list_steps(
    rule_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise NotFoundError("Rule", rule_id)
    steps = (
        db.query(PipelineStep)
        .filter(PipelineStep.rule_id == rule_id)
        .order_by(PipelineStep.order)
        .all()
    )
    return steps


@router.post("/{rule_id}/steps", response_model=PipelineStepOut, status_code=201)
def add_step(
    rule_id: int,
    payload: PipelineStepCreate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise NotFoundError("Rule", rule_id)

    # Auto-assign order to the end
    max_order = (
        db.query(PipelineStep.order)
        .filter(PipelineStep.rule_id == rule_id)
        .order_by(PipelineStep.order.desc())
        .first()
    )
    next_order = (max_order[0] + 1) if max_order else 0

    step = PipelineStep(
        rule_id=rule_id,
        order=next_order,
        **payload.model_dump(),
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


@router.put("/{rule_id}/steps/reorder", response_model=list[PipelineStepOut])
def reorder_steps(
    rule_id: int,
    payload: PipelineStepReorder,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise NotFoundError("Rule", rule_id)

    for new_order, step_id in enumerate(payload.steps):
        step = (
            db.query(PipelineStep)
            .filter(PipelineStep.id == step_id, PipelineStep.rule_id == rule_id)
            .first()
        )
        if step:
            step.order = new_order
    db.commit()

    return (
        db.query(PipelineStep)
        .filter(PipelineStep.rule_id == rule_id)
        .order_by(PipelineStep.order)
        .all()
    )


@router.put("/{rule_id}/steps/{step_id}", response_model=PipelineStepOut)
def update_step(
    rule_id: int,
    step_id: int,
    payload: PipelineStepUpdate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    step = (
        db.query(PipelineStep)
        .filter(PipelineStep.id == step_id, PipelineStep.rule_id == rule_id)
        .first()
    )
    if not step:
        raise NotFoundError("PipelineStep", step_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(step, key, value)
    db.commit()
    db.refresh(step)
    return step


@router.delete("/{rule_id}/steps/{step_id}", status_code=204)
def delete_step(
    rule_id: int,
    step_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    from backend.models.pipeline import WorkflowExecution

    step = (
        db.query(PipelineStep)
        .filter(PipelineStep.id == step_id, PipelineStep.rule_id == rule_id)
        .first()
    )
    if not step:
        raise NotFoundError("PipelineStep", step_id)

    # Clear inbound FK references before deleting
    db.query(WorkflowExecution).filter(WorkflowExecution.current_step_id == step_id).update(
        {"current_step_id": None}, synchronize_session=False
    )
    db.query(PipelineStep).filter(PipelineStep.next_step_on_true == step_id).update(
        {"next_step_on_true": None}, synchronize_session=False
    )
    db.query(PipelineStep).filter(PipelineStep.next_step_on_false == step_id).update(
        {"next_step_on_false": None}, synchronize_session=False
    )

    db.delete(step)
    db.commit()

    # Re-order remaining steps
    remaining = (
        db.query(PipelineStep)
        .filter(PipelineStep.rule_id == rule_id)
        .order_by(PipelineStep.order)
        .all()
    )
    for i, s in enumerate(remaining):
        s.order = i
    db.commit()


@router.post("/{rule_id}/execute", status_code=202)
async def execute_rule(
    rule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    """Manually trigger a rule for testing."""
    from backend.steps.base import TriggerContext

    rule = db.query(Rule).options(joinedload(Rule.steps)).filter(Rule.id == rule_id).first()
    if not rule:
        raise NotFoundError("Rule", rule_id)

    pipeline_executor = request.app.state.pipeline_executor

    # Gather media from primary sensor if available
    media_paths: list[str] = []
    if rule.primary_sensor_id and hasattr(request.app.state, "event_aggregator"):
        media_paths = await request.app.state.event_aggregator.get_recent_images(
            rule.primary_sensor_id, limit=3
        )

    trigger = TriggerContext(
        trigger_type="manual",
        sensor_id=rule.primary_sensor_id,
        media_paths=media_paths,
    )

    execution = await pipeline_executor.execute(rule, trigger, db)
    return {
        "execution_id": execution.id,
        "status": execution.status,
    }


# ---------------------------------------------------------------------------
# Contexts
# ---------------------------------------------------------------------------


@router.get("/{rule_id}/contexts", response_model=list[RuleContextOut])
def list_contexts(
    rule_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise NotFoundError("Rule", rule_id)
    return rule.contexts


@router.post("/{rule_id}/contexts", response_model=RuleContextOut, status_code=201)
def add_context(
    rule_id: int,
    payload: ContextCreate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise NotFoundError("Rule", rule_id)
    ctx = RuleContext(rule_id=rule_id, **payload.model_dump())
    db.add(ctx)
    db.commit()
    db.refresh(ctx)
    return ctx


@router.delete("/{rule_id}/contexts/{context_id}", status_code=204)
def delete_context(
    rule_id: int,
    context_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    ctx = (
        db.query(RuleContext)
        .filter(RuleContext.id == context_id, RuleContext.rule_id == rule_id)
        .first()
    )
    if not ctx:
        raise NotFoundError("RuleContext", context_id)
    db.delete(ctx)
    db.commit()


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


@router.get("/{rule_id}/dependencies", response_model=list[RuleDependencyOut])
def list_dependencies(
    rule_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise NotFoundError("Rule", rule_id)
    return rule.dependencies


@router.post("/{rule_id}/dependencies", response_model=RuleDependencyOut, status_code=201)
def add_dependency(
    rule_id: int,
    payload: DependencyCreate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise NotFoundError("Rule", rule_id)
    dep = RuleDependency(dependent_rule_id=rule_id, **payload.model_dump())
    db.add(dep)
    db.commit()
    db.refresh(dep)
    return dep


@router.delete("/{rule_id}/dependencies/{dep_id}", status_code=204)
def delete_dependency(
    rule_id: int,
    dep_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    dep = (
        db.query(RuleDependency)
        .filter(RuleDependency.id == dep_id, RuleDependency.dependent_rule_id == rule_id)
        .first()
    )
    if not dep:
        raise NotFoundError("RuleDependency", dep_id)
    db.delete(dep)
    db.commit()
