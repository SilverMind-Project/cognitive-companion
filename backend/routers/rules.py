"""Rule and pipeline step CRUD endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.models.cron_trigger import CronTrigger
from backend.models.pipeline import PipelineEdge, PipelineStep, WorkflowExecution
from backend.models.rule import Rule, RuleContext, RuleDependency
from backend.schemas.pipeline_types import (
    PipelineEdgeBulkUpdate,
    PipelineEdgeOut,
)
from backend.schemas.rule import (
    ContextCreate,
    CronTriggerCreate,
    CronTriggerOut,
    CronTriggerUpdate,
    DependencyCreate,
    PipelineStepCreate,
    PipelineStepOut,
    PipelineStepUpdate,
    RuleContextOut,
    RuleCreate,
    RuleDependencyOut,
    RuleExecutionCounts,
    RuleExecutionStartedOut,
    RuleListOut,
    RuleOut,
    RuleUpdate,
    RuleValidationOut,
)
from backend.schemas.rule_bundle import ImportReport, RuleBundle
from backend.services import rule_service
from backend.services.pipeline_graph import validate_gate_graph, validate_graph
from backend.services.rule_importer import bundle_to_rule
from backend.services.rule_serializer import rule_to_bundle, validate_bundle
from backend.services.step_config_validation import validate_step_config_schema
from backend.services.template_validator import validate_step_config

router = APIRouter(prefix="/rules", tags=["rules"])


class StepPositionUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    step_id: int
    position_x: float
    position_y: float


class BatchPositionUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    positions: list[StepPositionUpdate]


def _app_version() -> str:
    from importlib.metadata import version

    return version("cognitive-companion")


# ---------------------------------------------------------------------------
# Rules CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[RuleListOut])
def list_rules(
    callable: bool | None = None,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:read")),
) -> list[RuleListOut]:
    now = datetime.now(UTC)
    t_15m = now - timedelta(minutes=15)
    t_1h = now - timedelta(hours=1)
    t_24h = now - timedelta(hours=24)
    t_30d = now - timedelta(days=30)

    counts_sq = (
        db.query(
            WorkflowExecution.rule_id,
            func.count(case((WorkflowExecution.started_at >= t_15m, 1))).label("last_15m"),
            func.count(case((WorkflowExecution.started_at >= t_1h, 1))).label("last_1h"),
            func.count(case((WorkflowExecution.started_at >= t_24h, 1))).label("last_24h"),
            func.count(case((WorkflowExecution.started_at >= t_30d, 1))).label("last_30d"),
        )
        .group_by(WorkflowExecution.rule_id)
        .subquery()
    )

    rules = rule_service.list_rules(db, callable_only=callable is True)

    count_map: dict[int, RuleExecutionCounts] = {
        row.rule_id: RuleExecutionCounts(
            last_15m=row.last_15m or 0,
            last_1h=row.last_1h or 0,
            last_24h=row.last_24h or 0,
            last_30d=row.last_30d or 0,
        )
        for row in db.query(counts_sq).all()
    }

    result: list[RuleListOut] = []
    for rule in rules:
        out = RuleListOut.model_validate(rule)
        out.execution_counts = count_map.get(rule.id, RuleExecutionCounts())
        result.append(out)
    return result


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
        cron_triggers = db.query(CronTrigger).filter(CronTrigger.id.in_(cron_trigger_ids)).all()
        if len(cron_triggers) != len(cron_trigger_ids):
            raise NotFoundError(
                "CronTrigger", str(set(cron_trigger_ids) - {t.id for t in cron_triggers})
            )
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
    rule = rule_service.get_rule(db, rule_id)
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
        cron_triggers = db.query(CronTrigger).filter(CronTrigger.id.in_(cron_trigger_ids)).all()
        if len(cron_triggers) != len(cron_trigger_ids):
            raise NotFoundError(
                "CronTrigger", str(set(cron_trigger_ids) - {t.id for t in cron_triggers})
            )
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


@router.get("/{rule_id}/edges", response_model=list[PipelineEdgeOut])
def list_rule_edges(
    rule_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:read")),
) -> list[PipelineEdge]:
    rule = db.get(Rule, rule_id)
    if not rule:
        raise NotFoundError("Rule", rule_id)
    return (
        db.query(PipelineEdge)
        .filter(PipelineEdge.rule_id == rule_id)
        .order_by(PipelineEdge.id)
        .all()
    )


@router.put("/{rule_id}/edges", response_model=list[PipelineEdgeOut])
def replace_rule_edges(
    rule_id: int,
    payload: PipelineEdgeBulkUpdate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
) -> list[PipelineEdge]:
    rule = db.query(Rule).options(joinedload(Rule.steps)).filter(Rule.id == rule_id).first()
    if not rule:
        raise NotFoundError("Rule", rule_id)

    # Collapse exact-duplicate edges (same source port to the same target).
    # Fan-out (one source port to several distinct targets) is allowed; an
    # identical edge is redundant and would create a duplicate row.
    seen_edges: set[tuple[int, str, int, str]] = set()
    new_edges: list[PipelineEdge] = []
    for edge in payload.edges:
        key = (edge.source_step_id, edge.source_port, edge.target_step_id, edge.target_port)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        new_edges.append(
            PipelineEdge(
                rule_id=rule_id,
                source_step_id=edge.source_step_id,
                source_port=edge.source_port,
                target_step_id=edge.target_step_id,
                target_port=edge.target_port,
            )
        )

    _validate_rule_graph_or_raise(list(rule.steps), new_edges, is_callable=rule.is_callable)

    db.query(PipelineEdge).filter(PipelineEdge.rule_id == rule_id).delete(synchronize_session=False)
    db.add_all(new_edges)
    db.commit()

    return (
        db.query(PipelineEdge)
        .filter(PipelineEdge.rule_id == rule_id)
        .order_by(PipelineEdge.id)
        .all()
    )


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


def _assert_label_unique(
    db: Session, rule_id: int, label: str, exclude_step_id: int | None = None
) -> None:
    q = db.query(PipelineStep).filter(
        PipelineStep.rule_id == rule_id,
        PipelineStep.label == label,
    )
    if exclude_step_id is not None:
        q = q.filter(PipelineStep.id != exclude_step_id)
    if q.first():
        raise ConflictError(f"A step with label '{label}' already exists in this pipeline")


def _get_known_labels(db: Session, rule_id: int, exclude_step_id: int | None = None) -> list[str]:
    """Return the list of step labels for the given rule."""
    q = db.query(PipelineStep.label).filter(PipelineStep.rule_id == rule_id)
    if exclude_step_id is not None:
        q = q.filter(PipelineStep.id != exclude_step_id)
    return [row[0] for row in q.all()]


def _assert_valid_templates(step_type: str, config: dict, known_labels: list[str]) -> None:
    """Raise HTTPException 422 if the step config is schema-invalid or has a bad template."""
    schema_errors = validate_step_config_schema(step_type, config)
    template_errors = validate_step_config(step_type, config, known_labels)
    if schema_errors or template_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Step config validation failed",
                "errors": schema_errors + [e.to_dict() for e in template_errors],
            },
        )


def _collect_step_output_ports(steps: list[PipelineStep]) -> dict[int, tuple[str, ...]]:
    from backend.steps import StepRegistry

    StepRegistry.discover()
    output_ports: dict[int, tuple[str, ...]] = {}
    for step in steps:
        handler = StepRegistry.get(step.step_type)
        output_ports[step.id] = handler.metadata().output_ports if handler else ("main",)
    return output_ports


def _validate_rule_graph_or_raise(
    steps: list[PipelineStep], edges: list[PipelineEdge], is_callable: bool = False
) -> None:
    # Authoring-time validation: enforce structural integrity (unknown steps,
    # duplicate source ports, invalid ports, cycles) but NOT the single-entry
    # rule. A pipeline under construction routinely has unwired steps (multiple
    # entry nodes); that is reported as a non-blocking warning by the validate
    # endpoint and enforced at execution time, not on every edge save.
    if is_callable:
        from backend.steps import StepRegistry

        StepRegistry.discover()
        errors = validate_gate_graph(
            steps,
            edges,
            step_metadata=lambda t_name: h.metadata() if (h := StepRegistry.get(t_name)) else None,
            gate_safe_only=True,
        )
    else:
        errors = validate_graph(
            {step.id for step in steps},
            edges,
            _collect_step_output_ports(steps),
            check_entry=False,
        )
    if errors:
        raise ValidationError("; ".join(errors))


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
    # Validate template expressions
    known_labels = _get_known_labels(db, rule_id)
    if payload.label and payload.label not in known_labels:
        known_labels.append(payload.label)
    _assert_valid_templates(payload.step_type, payload.config_json or {}, known_labels)

    db.add(step)
    db.commit()
    db.refresh(step)
    return step


@router.put("/{rule_id}/steps/positions")
def batch_update_step_positions(
    rule_id: int,
    payload: BatchPositionUpdate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:write")),
) -> dict[str, int]:
    rule = db.query(Rule).options(joinedload(Rule.steps)).filter(Rule.id == rule_id).first()
    if not rule:
        raise NotFoundError("Rule", rule_id)

    step_ids = {step.id for step in rule.steps}
    for position in payload.positions:
        if position.step_id not in step_ids:
            raise ValidationError(f"Step {position.step_id} not in rule {rule_id}")
        db.query(PipelineStep).filter(
            PipelineStep.id == position.step_id,
            PipelineStep.rule_id == rule_id,
        ).update(
            {
                "position_x": position.position_x,
                "position_y": position.position_y,
            },
            synchronize_session=False,
        )

    db.commit()
    return {"updated": len(payload.positions)}


@router.put("/{rule_id}/steps/{step_id:int}", response_model=PipelineStepOut)
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

    # Validate template expressions if config is being updated
    if "config_json" in updates:
        effective_label = updates.get("label") or step.label
        effective_type = updates.get("step_type") or step.step_type
        known_labels = _get_known_labels(db, rule_id, exclude_step_id=step_id)
        if effective_label not in known_labels:
            known_labels.append(effective_label)
        _assert_valid_templates(effective_type, updates["config_json"] or {}, known_labels)

    for key, value in updates.items():
        setattr(step, key, value)
    db.commit()
    db.refresh(step)
    return step


@router.delete("/{rule_id}/steps/{step_id:int}", status_code=204)
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

    db.query(WorkflowExecution).filter(WorkflowExecution.current_step_id == step_id).update(
        {"current_step_id": None}, synchronize_session=False
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


@router.post("/{rule_id}/validate", response_model=RuleValidationOut)
def validate_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    """Lint all template expressions across every step in a rule.

    Returns a list of ``TemplateError`` dicts keyed by step label.
    """
    rule = db.get(Rule, rule_id)
    if not rule:
        raise NotFoundError("Rule", rule_id)

    steps = db.query(PipelineStep).filter(PipelineStep.rule_id == rule_id).all()
    known_labels = [s.label for s in steps]

    all_errors: dict[str, list[dict]] = {}
    for step in steps:
        config = step.config_json or {}
        errors = validate_step_config(step.step_type, config, known_labels)
        if errors:
            all_errors[step.label] = [e.to_dict() for e in errors]

    graph_errors: list[str] = []
    if steps:
        edges = db.query(PipelineEdge).filter(PipelineEdge.rule_id == rule_id).all()
        if rule.is_callable:
            from backend.steps import StepRegistry

            StepRegistry.discover()
            graph_errors = validate_gate_graph(
                steps,
                edges,
                step_metadata=lambda t_name: (
                    h.metadata() if (h := StepRegistry.get(t_name)) else None
                ),
                gate_safe_only=False,
            )
        else:
            graph_errors = validate_graph(
                {step.id for step in steps},
                edges,
                _collect_step_output_ports(steps),
            )

    return {
        "rule_id": rule_id,
        "errors": all_errors,
        "graph_errors": graph_errors,
        "valid": len(all_errors) == 0 and len(graph_errors) == 0,
    }


@router.post("/{rule_id}/execute", status_code=202, response_model=RuleExecutionStartedOut)
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


@router.get("/{rule_id}/export", response_model=RuleBundle)
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
            joinedload(Rule.edges),
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
    report = bundle_to_rule(bundle, db, app_version=_app_version())
    if report.status == "error":
        return report
    db.commit()
    return report
