"""Tests for DAG fields in rule bundle serialization."""

from __future__ import annotations

from backend.models.pipeline import PipelineEdge, PipelineStep
from backend.models.rule import Rule
from backend.services.rule_serializer import rule_to_bundle


def test_rule_to_bundle_includes_positions_and_edges(db_session):
    rule = Rule(
        name="edge-export",
        enabled=True,
        trigger_types=["manual"],
        cool_off_minutes=5,
        max_daily_triggers=3,
    )
    db_session.add(rule)
    db_session.flush()
    first = PipelineStep(
        rule_id=rule.id,
        order=0,
        step_type="condition",
        label="check",
        config_json={},
        position_x=10.0,
        position_y=20.0,
    )
    second = PipelineStep(
        rule_id=rule.id,
        order=1,
        step_type="notification",
        label="notify",
        config_json={},
        position_x=30.0,
        position_y=40.0,
    )
    db_session.add_all([first, second])
    db_session.flush()
    db_session.add(
        PipelineEdge(
            rule_id=rule.id,
            source_step_id=first.id,
            source_port="true",
            target_step_id=second.id,
            target_port="main",
        )
    )
    db_session.commit()

    loaded = db_session.get(Rule, rule.id)

    bundle = rule_to_bundle(loaded, app_version="1.0.0")

    assert bundle.steps[0].position_x == 10.0
    assert bundle.steps[0].position_y == 20.0
    assert len(bundle.edges) == 1
    assert bundle.edges[0].source_label == "check"
    assert bundle.edges[0].source_port == "true"
    assert bundle.edges[0].target_label == "notify"
