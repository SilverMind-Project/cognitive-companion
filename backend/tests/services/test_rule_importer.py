"""Tests for persisted rule bundle import."""

from __future__ import annotations

import pytest

from backend.core.exceptions import ConflictError
from backend.models.cron_trigger import CronTrigger
from backend.models.pipeline import PipelineEdge, PipelineStep
from backend.models.rule import Rule, RuleContext, RuleDependency
from backend.schemas.rule_bundle import (
    ContextBundle,
    CronExpressionRef,
    DependencyBundle,
    EdgeBundle,
    RuleBundle,
    RuleDefinition,
    StepBundle,
)
from backend.services.rule_importer import bundle_to_rule
from backend.steps import StepRegistry

StepRegistry.discover()


def _bundle(
    name: str,
    *,
    steps: list[StepBundle] | None = None,
    contexts: list[ContextBundle] | None = None,
    edges: list[EdgeBundle] | None = None,
    dependencies: list[DependencyBundle] | None = None,
) -> RuleBundle:
    return RuleBundle(
        rule=RuleDefinition(
            name=name,
            enabled=True,
            trigger_types=["manual"],
            cron_expressions=[CronExpressionRef(expression="0 9 * * *", timezone="UTC")],
        ),
        contexts=contexts or [],
        steps=steps or [_notification_step("notify")],
        edges=edges or [],
        dependencies=dependencies or [],
    )


def _notification_step(label: str) -> StepBundle:
    return StepBundle(
        label=label,
        step_type="notification",
        config={},
    )


def _condition_step(label: str) -> StepBundle:
    return StepBundle(
        label=label,
        step_type="condition",
        config={"expression": "true"},
    )


def test_bundle_to_rule_creates_rule_steps_contexts(db_session):
    bundle = _bundle(
        "import-basic",
        contexts=[
            ContextBundle(
                context_type="time_range",
                config={"start_time": "08:00", "end_time": "20:00"},
                negate=True,
            )
        ],
    )

    report = bundle_to_rule(bundle, db_session, app_version="1.0.0")
    db_session.commit()

    assert report.status == "ok"
    rule = db_session.get(Rule, report.rule_id)
    assert rule is not None
    assert rule.name == "import-basic"
    assert db_session.query(PipelineStep).filter(PipelineStep.rule_id == rule.id).count() == 1
    assert db_session.query(RuleContext).filter(RuleContext.rule_id == rule.id).count() == 1
    assert (
        db_session.query(CronTrigger)
        .join(CronTrigger.rules)
        .filter(Rule.id == rule.id)
        .count()
        == 1
    )


def test_bundle_to_rule_creates_edges(db_session):
    bundle = _bundle(
        "import-edges",
        steps=[_condition_step("check"), _notification_step("notify")],
        edges=[
            EdgeBundle(
                source_label="check",
                source_port="true",
                target_label="notify",
                target_port="main",
            )
        ],
    )

    report = bundle_to_rule(bundle, db_session, app_version="1.0.0")
    db_session.commit()

    edges = db_session.query(PipelineEdge).filter(PipelineEdge.rule_id == report.rule_id).all()
    steps = {
        step.label: step
        for step in db_session.query(PipelineStep)
        .filter(PipelineStep.rule_id == report.rule_id)
        .all()
    }
    assert len(edges) == 1
    assert edges[0].source_step_id == steps["check"].id
    assert edges[0].source_port == "true"
    assert edges[0].target_step_id == steps["notify"].id


def test_bundle_to_rule_raises_conflict_on_duplicate_name(db_session):
    db_session.add(Rule(name="duplicate", enabled=True, trigger_types=["manual"]))
    db_session.commit()

    with pytest.raises(ConflictError):
        bundle_to_rule(_bundle("duplicate"), db_session, app_version="1.0.0")


def test_bundle_to_rule_warns_on_unresolved_dependency(db_session):
    bundle = _bundle(
        "import-unresolved-dep",
        dependencies=[
            DependencyBundle(
                parent_rule_name="missing-parent",
                lookback_minutes=15,
                require_success=False,
            )
        ],
    )

    report = bundle_to_rule(bundle, db_session, app_version="1.0.0")
    db_session.commit()

    assert report.status == "ok"
    assert any("missing-parent" in warning for warning in report.warnings)
    assert (
        db_session.query(RuleDependency)
        .filter(RuleDependency.dependent_rule_id == report.rule_id)
        .count()
        == 0
    )
