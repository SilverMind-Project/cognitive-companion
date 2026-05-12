"""Rule and pipeline step CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, joinedload

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.exceptions import ConflictError, NotFoundError
from backend.models.cron_trigger import CronTrigger
from backend.models.pipeline import PipelineStep
from backend.models.rule import Rule, RuleContext, RuleDependency
from backend.schemas.rule import (
    ContextCreate,
    CronTriggerCreate,
    CronTriggerOut,
    CronTriggerUpdate,
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
from backend.schemas.rule_bundle import ImportReport, RuleBundle
from backend.services.rule_serializer import rule_to_bundle, validate_bundle

router = APIRouter(prefix="/rules", tags=["rules"])


def _app_version() -> str:
    from importlib.metadata import version
    return version("cognitive-companion")


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

    # Separate cron_trigger_ids from the ORM fields
    data = payload.model_dump()
    cron_trigger_ids: list[int] = data.pop("cron_trigger_ids", [])

    rule = Rule(**data)
    if cron_trigger_ids:
        cron_triggers = (
            db.query(CronTrigger).filter(CronTrigger.id.in_(cron_trigger_ids)).all()
        )
        if len(cron_triggers) != len(cron_trigger_ids):
            raise NotFoundError("CronTrigger", str(set(cron_trigger_ids) - {t.id for t in cron_triggers}))
        rule.cron_triggers = cron_triggers
        if "cron" not in rule.trigger_types:
            rule.trigger_types = [*rule.trigger_types, "cron"]

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
            joinedload(Rule.cron_triggers),
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

    updates = payload.model_dump(exclude_unset=True)
    cron_trigger_ids: list[int] | None = updates.pop("cron_trigger_ids", None)

    for key, value in updates.items():
        setattr(rule, key, value)

    if cron_trigger_ids is not None:
        cron_triggers = (
            db.query(CronTrigger).filter(CronTrigger.id.in_(cron_trigger_ids)).all()
        )
        if len(cron_triggers) != len(cron_trigger_ids):
            raise NotFoundError("CronTrigger", str(set(cron_trigger_ids) - {t.id for t in cron_triggers}))
        rule.cron_triggers = cron_triggers
        if cron_triggers and "cron" not in rule.trigger_types:
            rule.trigger_types = [*rule.trigger_types, "cron"]
        elif not cron_triggers and "cron" in rule.trigger_types:
            rule.trigger_types = [t for t in rule.trigger_types if t != "cron"]

    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    from backend.models.cron_trigger import RuleCronTrigger
    from backend.models.event import EventLog
    from backend.models.pipeline import WorkflowExecution

    rule = db.get(Rule, rule_id)
    if not rule:
        raise NotFoundError("Rule", rule_id)

    # Clean up cron trigger join table
    db.query(RuleCronTrigger).filter(RuleCronTrigger.rule_id == rule_id).delete(
        synchronize_session=False
    )

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


def _generate_default_label(db: Session, rule_id: int, step_type: str) -> str:
    """Return a unique default label like ``llm_call_1`` for the given step type."""
    existing_labels = {
        row[0]
        for row in db.query(PipelineStep.label)
        .filter(PipelineStep.rule_id == rule_id, PipelineStep.label.isnot(None))
        .all()
    }
    n = 1
    while True:
        candidate = f"{step_type}_{n}"
        if candidate not in existing_labels:
            return candidate
        n += 1


def _assert_label_unique(db: Session, rule_id: int, label: str, exclude_step_id: int | None = None) -> None:
    q = db.query(PipelineStep).filter(
        PipelineStep.rule_id == rule_id,
        PipelineStep.label == label,
    )
    if exclude_step_id is not None:
        q = q.filter(PipelineStep.id != exclude_step_id)
    if q.first():
        raise ConflictError(f"A step with label '{label}' already exists in this pipeline")


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

    label = payload.label or _generate_default_label(db, rule_id, payload.step_type)
    _assert_label_unique(db, rule_id, label)

    data = payload.model_dump()
    data["label"] = label
    step = PipelineStep(
        rule_id=rule_id,
        order=next_order,
        **data,
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
    updates = payload.model_dump(exclude_unset=True)
    if "label" in updates and updates["label"] is not None:
        _assert_label_unique(db, rule_id, updates["label"], exclude_step_id=step_id)
    for key, value in updates.items():
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
    """Manually trigger a rule for testing. Works for any rule regardless of trigger_type."""
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


# ---------------------------------------------------------------------------
# Cron Triggers
# ---------------------------------------------------------------------------


@router.get("/cron-triggers", response_model=list[CronTriggerOut])
def list_cron_triggers(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    return db.query(CronTrigger).order_by(CronTrigger.name).all()


@router.post("/cron-triggers", response_model=CronTriggerOut, status_code=201)
def create_cron_trigger(
    payload: CronTriggerCreate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    ct = CronTrigger(**payload.model_dump())
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return ct


@router.put("/cron-triggers/{ct_id}", response_model=CronTriggerOut)
def update_cron_trigger(
    ct_id: int,
    payload: CronTriggerUpdate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    ct = db.get(CronTrigger, ct_id)
    if not ct:
        raise NotFoundError("CronTrigger", ct_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(ct, key, value)
    db.commit()
    db.refresh(ct)
    return ct


@router.delete("/cron-triggers/{ct_id}", status_code=204)
def delete_cron_trigger(
    ct_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    from backend.models.cron_trigger import RuleCronTrigger

    ct = db.get(CronTrigger, ct_id)
    if not ct:
        raise NotFoundError("CronTrigger", ct_id)

    db.query(RuleCronTrigger).filter(RuleCronTrigger.cron_trigger_id == ct_id).delete(
        synchronize_session=False
    )
    db.delete(ct)
    db.commit()


# ---------------------------------------------------------------------------
# Import / Export
# ---------------------------------------------------------------------------


@router.get("/{rule_id}/export")
def export_rule(
    rule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    """Export a rule as a portable YAML bundle."""
    rule = (
        db.query(Rule)
        .options(
            joinedload(Rule.steps),
            joinedload(Rule.contexts),
            joinedload(Rule.dependencies),
            joinedload(Rule.cron_triggers),
        )
        .filter(Rule.id == rule_id)
        .first()
    )
    if not rule:
        raise NotFoundError("Rule", rule_id)

    bundle = rule_to_bundle(rule, app_version=_app_version())
    return bundle.model_dump(mode="json")


@router.post("/import/preview", response_model=ImportReport)
def preview_import(
    bundle: RuleBundle,
    request: Request,
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    """Validate an import bundle without committing."""
    return validate_bundle(bundle, _app_version())


@router.post("/import", response_model=ImportReport, status_code=201)
def import_rule(
    bundle: RuleBundle,
    request: Request,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
):
    """Import a rule from a portable bundle. All-or-nothing within a transaction."""
    from backend.models.pipeline import PipelineStep

    # Validate first
    report = validate_bundle(bundle, _app_version())
    if report.status == "error":
        return report

    # Check for name conflict
    existing = db.query(Rule).filter(Rule.name == bundle.rule.name).first()
    if existing:
        raise ConflictError(f"Rule '{bundle.rule.name}' already exists")

    rule_def = bundle.rule

    # Create rule
    rule = Rule(
        name=rule_def.name,
        description=rule_def.description,
        enabled=rule_def.enabled,
        trigger_types=rule_def.trigger_types,
        primary_sensor_id=rule_def.primary_sensor_ref.label
        if rule_def.primary_sensor_ref
        else None,
        cool_off_minutes=rule_def.cool_off_minutes,
        max_daily_triggers=rule_def.max_daily_triggers,
        max_concurrent_executions=rule_def.max_concurrent_executions,
        execution_timeout_minutes=rule_def.execution_timeout_minutes,
        webhook_config=rule_def.webhook_config,
        occupancy_config=rule_def.occupancy_config,
        telegram_trigger_config=rule_def.telegram_trigger_config,
    )
    db.add(rule)
    db.flush()

    # Create cron triggers
    for ce in rule_def.cron_expressions:
        ct = CronTrigger(
            name=f"{rule_def.name} ({ce.expression})",
            expression=ce.expression,
            timezone=ce.timezone,
        )
        db.add(ct)
        db.flush()
        rule.cron_triggers.append(ct)

    # Create contexts
    for ctx_bundle in bundle.contexts:
        ctx = RuleContext(
            rule_id=rule.id,
            context_type=ctx_bundle.context_type,
            config_json=ctx_bundle.config,
            negate=ctx_bundle.negate,
        )
        db.add(ctx)

    # Create steps
    step_id_map: dict[str, int] = {}
    for i, step_bundle in enumerate(bundle.steps):
        step = PipelineStep(
            rule_id=rule.id,
            order=i,
            step_type=step_bundle.step_type,
            label=step_bundle.label,
            config_json=step_bundle.config,
            enabled=step_bundle.enabled,
        )
        db.add(step)
        db.flush()
        step_id_map[step_bundle.label] = step.id

    # Wire up branch targets (now that all steps have ids)
    for step_bundle in bundle.steps:
        step_id = step_id_map[step_bundle.label]
        step = db.get(PipelineStep, step_id)
        if step and step_bundle.branches.on_true:
            step.next_step_on_true = step_id_map.get(step_bundle.branches.on_true)
        if step and step_bundle.branches.on_false:
            step.next_step_on_false = step_id_map.get(step_bundle.branches.on_false)

    # Create dependencies (resolved by rule name)
    for dep_bundle in bundle.dependencies:
        parent = db.query(Rule).filter(Rule.name == dep_bundle.parent_rule_name).first()
        if parent:
            dep = RuleDependency(
                dependent_rule_id=rule.id,
                parent_rule_id=parent.id,
                lookback_minutes=dep_bundle.lookback_minutes,
                require_success=dep_bundle.require_success,
            )
            db.add(dep)
        else:
            report.warnings.append(
                f"Dependency on rule '{dep_bundle.parent_rule_name}' could not be resolved; skipped"
            )

    db.commit()
    db.refresh(rule)

    report.rule_id = rule.id
    report.status = "ok"
    return report
