"""Pure functions to serialize/deserialize rules to portable bundles.

No database access. The caller is responsible for loading ORM objects
and resolving external references.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.models.rule import Rule
from backend.schemas.rule_bundle import (
    ContextBundle,
    CronExpressionRef,
    DependencyBundle,
    EdgeBundle,
    ImportReport,
    ReferenceBlock,
    RuleBundle,
    RuleDefinition,
    SensorRef,
    SourceInfo,
    StepBundle,
    StepImportResult,
)


def rule_to_bundle(
    rule: Rule,
    *,
    app_version: str,
    exported_by: str | None = None,
) -> RuleBundle:
    """Serialize a Rule and its related objects to a portable bundle."""
    now = datetime.now(UTC)

    # Collect external references
    sensor_ids: list[str] = []
    if rule.primary_sensor_id:
        sensor_ids.append(rule.primary_sensor_id)

    llm_models: set[str] = set()
    for step in rule.steps:
        cfg = step.config_json or {}
        if "model_id" in cfg:
            llm_models.add(str(cfg["model_id"]))

    channels: list[str] = []
    for ctx in rule.contexts:
        cfg = ctx.config_json or {}
        if "channels" in cfg:
            channels.extend(cfg["channels"])

    # Person references come from step configs
    persons: set[str] = set()
    for step in rule.steps:
        cfg = step.config_json or {}
        for key in ("target_persons", "person_id", "person_ids"):
            val = cfg.get(key)
            if isinstance(val, list):
                persons.update(str(v) for v in val)
            elif val:
                persons.add(str(val))

    step_label_by_id = {step.id: step.label for step in rule.steps}
    edges: list[EdgeBundle] = []
    for edge in rule.edges:
        source_label = step_label_by_id.get(edge.source_step_id)
        target_label = step_label_by_id.get(edge.target_step_id)
        if source_label and target_label:
            edges.append(
                EdgeBundle(
                    source_label=source_label,
                    source_port=edge.source_port,
                    target_label=target_label,
                    target_port=edge.target_port,
                )
            )

    return RuleBundle(
        exported_at=now,
        exported_by=exported_by,
        source=SourceInfo(app_version=app_version),
        rule=RuleDefinition(
            name=rule.name,
            description=rule.description,
            enabled=rule.enabled,
            trigger_types=list(rule.trigger_types),
            primary_sensor_ref=SensorRef(label=rule.primary_sensor_id)
            if rule.primary_sensor_id
            else None,
            cool_off_minutes=rule.cool_off_minutes,
            max_daily_triggers=rule.max_daily_triggers,
            max_concurrent_executions=rule.max_concurrent_executions,
            execution_timeout_minutes=rule.execution_timeout_minutes,
            webhook_config=rule.webhook_config,
            occupancy_config=rule.occupancy_config,
            telegram_trigger_config=rule.telegram_trigger_config,
            cron_expressions=[
                CronExpressionRef(expression=ct.expression, timezone=ct.timezone)
                for ct in rule.cron_triggers
            ],
        ),
        references=ReferenceBlock(
            sensors=sorted(sensor_ids),
            persons=sorted(persons),
            channels=sorted(set(channels)),
            llm_models=sorted(llm_models),
        ),
        contexts=[
            ContextBundle(
                context_type=ctx.context_type,
                config=ctx.config_json or {},
                negate=ctx.negate,
            )
            for ctx in rule.contexts
        ],
        steps=[
            StepBundle(
                label=step.label or step.step_type,
                step_type=step.step_type,
                enabled=step.enabled,
                position_x=step.position_x,
                position_y=step.position_y,
                config=step.config_json or {},
            )
            for step in sorted(rule.steps, key=lambda s: s.order)
        ],
        edges=edges,
        dependencies=[
            DependencyBundle(
                parent_rule_name=dep.parent_rule.name,
                lookback_minutes=dep.lookback_minutes,
                require_success=dep.require_success,
            )
            for dep in (rule.dependencies or [])
        ],
    )


def validate_bundle(bundle: RuleBundle, current_app_version: str) -> ImportReport:
    """Validate a bundle for import without writing to the database.

    Returns an ImportReport with per-step status and any warnings/errors.
    """
    report = ImportReport(rule_name=bundle.rule.name, status="ok")

    # Check min app version
    if (
        bundle.source
        and bundle.source.app_version
        and _version_gt(bundle.source.app_version, current_app_version)
    ):
        report.warnings.append(
            f"Bundle was exported from CC v{bundle.source.app_version}. "
            f"You are running v{current_app_version}. Some features may not be available."
        )
        report.min_app_version_required = bundle.source.app_version

    # Validate steps

    for step_bundle in bundle.steps:
        handler_meta = _get_step_metadata(step_bundle.step_type)
        if handler_meta is None:
            report.steps.append(
                StepImportResult(
                    label=step_bundle.label,
                    step_type=step_bundle.step_type,
                    status="error",
                    description=f"Unknown step type: {step_bundle.step_type}",
                )
            )
            report.errors.append(
                f"Step '{step_bundle.label}': unknown type '{step_bundle.step_type}'"
            )
            report.status = "error"
            continue

        # Check schema version compatibility
        if step_bundle.schema_version > handler_meta.schema_version:
            report.steps.append(
                StepImportResult(
                    label=step_bundle.label,
                    step_type=step_bundle.step_type,
                    status="warning",
                    description=(
                        f"Step schema v{step_bundle.schema_version} is newer than "
                        f"current v{handler_meta.schema_version}. Config may be downgraded."
                    ),
                )
            )
        elif step_bundle.schema_version < handler_meta.schema_version:
            report.steps.append(
                StepImportResult(
                    label=step_bundle.label,
                    step_type=step_bundle.step_type,
                    status="migrated",
                    description=(
                        f"Will migrate from v{step_bundle.schema_version} "
                        f"to v{handler_meta.schema_version}"
                    ),
                )
            )
        else:
            report.steps.append(
                StepImportResult(
                    label=step_bundle.label,
                    step_type=step_bundle.step_type,
                    status="ok",
                    description="Config matches current schema version",
                )
            )

    # Validate context types
    from backend.filters import FilterRegistry

    for ctx_bundle in bundle.contexts:
        if FilterRegistry.get(ctx_bundle.context_type) is None:
            report.warnings.append(
                f"Context '{ctx_bundle.context_type}': unknown filter type, will be skipped"
            )

    # Validate cron expressions
    if bundle.rule.cron_expressions:
        from apscheduler.triggers.cron import CronTrigger as _CronTrigger

        for i, ce in enumerate(bundle.rule.cron_expressions):
            try:
                _CronTrigger.from_crontab(ce.expression)
            except ValueError, TypeError:
                report.errors.append(f"Cron expression {i}: '{ce.expression}' is not valid")
                report.status = "error"

    return report


# -- helpers ------------------------------------------------------------------


def _get_step_metadata(step_type: str):
    from backend.steps import StepRegistry

    handler = StepRegistry.get(step_type)
    if handler is None:
        return None
    return handler.metadata()


def _version_gt(a: str, b: str) -> bool:
    """Compare semantic version strings. Returns True if a > b."""
    try:
        a_parts = tuple(int(x) for x in a.split("."))
        b_parts = tuple(int(x) for x in b.split("."))
        return a_parts > b_parts
    except ValueError, TypeError:
        return a != b
