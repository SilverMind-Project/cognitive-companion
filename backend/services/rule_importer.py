"""Persist portable rule bundles into the database."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.core.exceptions import ConflictError, ValidationError
from backend.models.cron_trigger import CronTrigger
from backend.models.pipeline import PipelineEdge, PipelineStep
from backend.models.rule import Rule, RuleContext, RuleDependency
from backend.schemas.rule_bundle import ImportReport, RuleBundle
from backend.services.pipeline_graph import validate_graph
from backend.services.rule_serializer import validate_bundle


def bundle_to_rule(
    bundle: RuleBundle,
    db: Session,
    *,
    app_version: str,
) -> ImportReport:
    """Validate and persist a ``RuleBundle`` within the caller's transaction."""
    report = validate_bundle(bundle, app_version)
    if report.status == "error":
        return report

    existing = db.query(Rule).filter(Rule.name == bundle.rule.name).first()
    if existing:
        raise ConflictError(f"Rule '{bundle.rule.name}' already exists")

    rule_def = bundle.rule
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

    for ce in rule_def.cron_expressions:
        ct = CronTrigger(
            name=f"{rule_def.name} ({ce.expression})",
            expression=ce.expression,
            timezone=ce.timezone,
        )
        db.add(ct)
        db.flush()
        rule.cron_triggers.append(ct)

    for ctx_bundle in bundle.contexts:
        ctx = RuleContext(
            rule_id=rule.id,
            context_type=ctx_bundle.context_type,
            config_json=ctx_bundle.config,
            negate=ctx_bundle.negate,
        )
        db.add(ctx)

    step_id_map: dict[str, int] = {}
    for i, step_bundle in enumerate(bundle.steps):
        step = PipelineStep(
            rule_id=rule.id,
            order=i,
            step_type=step_bundle.step_type,
            label=step_bundle.label,
            config_json=step_bundle.config,
            enabled=step_bundle.enabled,
            position_x=step_bundle.position_x,
            position_y=step_bundle.position_y,
        )
        db.add(step)
        db.flush()
        step_id_map[step_bundle.label] = step.id

    new_edges: list[PipelineEdge] = []
    for edge_bundle in bundle.edges:
        source_id = step_id_map.get(edge_bundle.source_label)
        target_id = step_id_map.get(edge_bundle.target_label)
        if source_id is None or target_id is None:
            report.warnings.append(
                f"Edge {edge_bundle.source_label}:{edge_bundle.source_port} -> "
                f"{edge_bundle.target_label} skipped: label not found"
            )
            continue

        edge = PipelineEdge(
            rule_id=rule.id,
            source_step_id=source_id,
            source_port=edge_bundle.source_port,
            target_step_id=target_id,
            target_port=edge_bundle.target_port,
        )
        db.add(edge)
        new_edges.append(edge)

    if bundle.edges:
        created_steps = (
            db.query(PipelineStep)
            .filter(PipelineStep.rule_id == rule.id)
            .order_by(PipelineStep.order)
            .all()
        )
        try:
            _validate_rule_graph_or_raise(created_steps, new_edges)
        except ValidationError:
            db.rollback()
            raise

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

    report.rule_id = rule.id
    report.status = "ok"
    return report


def _collect_step_output_ports(steps: list[PipelineStep]) -> dict[int, tuple[str, ...]]:
    from backend.steps import StepRegistry

    StepRegistry.discover()
    output_ports: dict[int, tuple[str, ...]] = {}
    for step in steps:
        handler = StepRegistry.get(step.step_type)
        output_ports[step.id] = handler.metadata().output_ports if handler else ("main",)
    return output_ports


def _validate_rule_graph_or_raise(steps: list[PipelineStep], edges: list[PipelineEdge]) -> None:
    errors = validate_graph(
        {step.id for step in steps},
        edges,
        _collect_step_output_ports(steps),
    )
    if errors:
        raise ValidationError("; ".join(errors))
