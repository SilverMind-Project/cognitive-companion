"""Gate-graph CRUD, validation, preset, and test-run endpoints (VG08).

A gate graph is a callable ``Rule`` (``trigger_types == []``, D21). These
endpoints are a thin gate-scoped surface over the shared rule service: listing
reuses ``rule_service.list_rules`` with the callable filter and detail reuses
``rule_service.get_rule`` (no parallel query). Step/edge editing continues to
use the existing ``/rules/{id}`` endpoints and the canvas; only the
gate-specific concerns (callable filter, preset cloning, full gate validation,
preview) live here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.exceptions import ConflictError, NotFoundError
from backend.models.pipeline import PipelineEdge, PipelineStep
from backend.models.rule import Rule
from backend.schemas.gate_graph import (
    GateGraphCreate,
    GateGraphDetail,
    GateGraphListEnvelope,
    GatePresetOut,
    GateTestRunRequest,
    GateValidateResult,
    GateVerdictOut,
)
from backend.schemas.rule import RuleListOut, RuleOut
from backend.services import rule_service
from backend.services.guided_task import gate_presets
from backend.services.pipeline_graph import validate_gate_graph
from backend.services.template_validator import validate_step_config

router = APIRouter(prefix="/gate-graphs", tags=["gate-graphs"])
presets_router = APIRouter(prefix="/gate-presets", tags=["gate-graphs"])


def _gate_metadata(t_name: str):
    from backend.steps import StepRegistry

    StepRegistry.discover()
    handler = StepRegistry.get(t_name)
    return handler.metadata() if handler else None


@router.get("", response_model=GateGraphListEnvelope)
def list_gate_graphs(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("gate_graphs:read")),
) -> GateGraphListEnvelope:
    rules = rule_service.list_rules(db, callable_only=True)
    items = [RuleListOut.model_validate(r) for r in rules]
    return GateGraphListEnvelope(items=items, total=len(items))


@router.post("", response_model=RuleOut, status_code=201)
def create_gate_graph(
    payload: GateGraphCreate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("gate_graphs:write")),
) -> Rule:
    existing = db.query(Rule).filter(Rule.name == payload.name).first()
    if existing:
        raise ConflictError(f"Rule '{payload.name}' already exists")

    if payload.from_preset is not None:
        preset = gate_presets.get_preset(payload.from_preset)
        if preset is None:
            raise NotFoundError("GatePreset", payload.from_preset)
        # Build a fresh callable rule through the shared factory (clones the
        # preset's steps/edges with their labels/positions preserved).
        rule = preset.build(db, payload.name)
        if payload.description is not None:
            rule.description = payload.description
    else:
        rule = Rule(
            name=payload.name, description=payload.description, enabled=True, trigger_types=[]
        )
        db.add(rule)

    db.commit()
    db.refresh(rule)
    return rule


@router.get("/{rule_id}", response_model=GateGraphDetail)
def get_gate_graph(
    rule_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("gate_graphs:read")),
) -> GateGraphDetail:
    rule = rule_service.get_rule(db, rule_id)
    if not rule or not rule.is_callable:
        raise NotFoundError("GateGraph", rule_id)
    edges = (
        db.query(PipelineEdge)
        .filter(PipelineEdge.rule_id == rule_id)
        .order_by(PipelineEdge.id)
        .all()
    )
    return GateGraphDetail(
        rule=RuleOut.model_validate(rule),
        steps=sorted(rule.steps, key=lambda s: s.order),
        edges=edges,
    )


@router.post("/{rule_id}/validate", response_model=GateValidateResult)
def validate_gate_graph_endpoint(
    rule_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("gate_graphs:write")),
) -> GateValidateResult:
    rule = db.get(Rule, rule_id)
    if not rule:
        raise NotFoundError("GateGraph", rule_id)

    steps = db.query(PipelineStep).filter(PipelineStep.rule_id == rule_id).all()
    edges = db.query(PipelineEdge).filter(PipelineEdge.rule_id == rule_id).all()

    # Full gate validation: exactly one reachable gate_verdict + all gate-safe.
    errors = validate_gate_graph(steps, edges, step_metadata=_gate_metadata, gate_safe_only=False)

    # Per-step template expression linting (mirrors POST /rules/{id}/validate).
    known_labels = [s.label for s in steps]
    template_errors: dict[str, list[dict]] = {}
    for step in steps:
        step_errors = validate_step_config(step.step_type, step.config_json or {}, known_labels)
        if step_errors:
            template_errors[step.label] = [e.to_dict() for e in step_errors]

    return GateValidateResult(
        valid=not errors and not template_errors,
        errors=errors,
        template_errors=template_errors,
    )


@router.post("/{rule_id}/test-run", response_model=GateVerdictOut)
async def preview_gate_graph(
    rule_id: int,
    payload: GateTestRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("gate_graphs:write")),
) -> GateVerdictOut:
    rule = db.get(Rule, rule_id)
    if not rule or not rule.is_callable:
        raise NotFoundError("GateGraph", rule_id)

    guided_task_service = getattr(request.app.state, "guided_task_service", None)
    if guided_task_service is None:
        # Fail closed: never 500 a preview.
        return GateVerdictOut(
            complete=False,
            confidence=0.0,
            reason="gate_service_unavailable",
            node_results={},
            cost={"model_calls": 0, "frames": 0, "latency_ms": 0},
            profile=payload.profile,
        )

    verdict = await guided_task_service.run_gate_preview(
        gate_rule_id=rule_id,
        person_id=payload.person_id,
        room_name=payload.room_name,
        sensor_id=payload.sensor_id,
        profile_name=payload.profile,
        camera_ids=payload.camera_ids,
        zone_id=payload.zone_id,
    )
    return GateVerdictOut(
        complete=verdict.complete,
        confidence=verdict.confidence,
        reason=verdict.reason,
        node_results=verdict.node_results,
        cost=verdict.cost,
        profile=verdict.profile,
    )


@presets_router.get("", response_model=list[GatePresetOut])
def list_gate_presets(
    _auth: AuthContext = Depends(require_permission("gate_graphs:read")),
) -> list[GatePresetOut]:
    return [
        GatePresetOut(key=p.key, name=p.name, description=p.description, summary=p.summary)
        for p in gate_presets.list_presets()
    ]
