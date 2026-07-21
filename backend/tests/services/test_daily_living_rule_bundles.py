"""DL-M04 Part C.2: the four daily-living activity-ledger rule bundles import
cleanly onto a fresh DB with the expected triggers, filters, and step types.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.filters import FilterRegistry
from backend.models.pipeline import PipelineEdge, PipelineStep
from backend.models.rule import Rule, RuleContext
from backend.schemas.rule_bundle import RuleBundle
from backend.services.rule_importer import bundle_to_rule
from backend.steps import StepRegistry

StepRegistry.discover()
FilterRegistry.discover()

_BUNDLE_DIR = Path(__file__).resolve().parents[3] / "config" / "rule_bundles"

_PLACEHOLDERS = {
    "__RESIDENT_PERSON_ID__": "test_resident",
    "__TV_ROOM_NAME__": "living_room",
    "__TV_MEDIA_PLAYER_ENTITY__": "media_player.test_tv",
    "__DINING_ROOM_NAME__": "dining_room",
    "__DINING_CAMERA_SENSOR_ID__": "test_dining_cam",
}

_BUNDLE_FILES = (
    "daily_living_tv_open.json",
    "daily_living_tv_close.json",
    "daily_living_meal_open.json",
    "daily_living_meal_close.json",
)


def _load_bundle(filename: str) -> RuleBundle:
    raw = (_BUNDLE_DIR / filename).read_text()
    for placeholder, value in _PLACEHOLDERS.items():
        raw = raw.replace(placeholder, value)
    return RuleBundle(**json.loads(raw))


@pytest.fixture
def imported_rules(db_session) -> dict[str, Rule]:
    rules: dict[str, Rule] = {}
    for filename in _BUNDLE_FILES:
        bundle = _load_bundle(filename)
        report = bundle_to_rule(bundle, db_session, app_version="test")
        assert report.status == "ok", (filename, report.errors)
        db_session.commit()
        rules[bundle.rule.name] = db_session.get(Rule, report.rule_id)
    return rules


def test_all_four_bundles_import_as_enabled_rules(imported_rules):
    assert len(imported_rules) == 4
    for name, rule in imported_rules.items():
        assert rule is not None, name
        assert rule.enabled is True, name
        assert rule.trigger_types == ["cron"], name


def test_bundles_have_no_daily_trigger_or_cooloff_limit(imported_rules):
    # These rules poll every 2-10 minutes and rely on idempotent open/close
    # semantics rather than rate limiting (DL-M04 finding: the default
    # max_daily_triggers=3 would silence them after three ticks).
    for rule in imported_rules.values():
        assert rule.max_daily_triggers == 0
        assert rule.cool_off_minutes == 0


def test_tv_open_has_home_state_and_presence_status_filters(imported_rules, db_session):
    rule = imported_rules["daily_living_tv_open"]
    contexts = db_session.query(RuleContext).filter(RuleContext.rule_id == rule.id).all()
    context_types = {c.context_type for c in contexts}
    assert context_types == {"home_state", "presence_status"}

    home_state_ctx = next(c for c in contexts if c.context_type == "home_state")
    assert home_state_ctx.config_json["entity_id"] == "media_player.test_tv"
    assert "playing" in home_state_ctx.config_json["states_any"]

    steps = db_session.query(PipelineStep).filter(PipelineStep.rule_id == rule.id).all()
    assert [s.step_type for s in steps] == ["activity_session_start"]
    assert steps[0].config_json["activity_type"] == "watching_tv"


def test_tv_close_chain_and_condition(imported_rules, db_session):
    rule = imported_rules["daily_living_tv_close"]
    steps = {
        s.label: s
        for s in db_session.query(PipelineStep).filter(PipelineStep.rule_id == rule.id).all()
    }
    assert set(steps) == {"presence", "tv_state", "should_close", "end"}
    assert steps["presence"].step_type == "presence_query"
    assert steps["tv_state"].step_type == "home_state"
    assert steps["should_close"].step_type == "condition"
    assert steps["end"].step_type == "activity_session_end"
    assert steps["end"].config_json["activity_type"] == "watching_tv"

    edges = db_session.query(PipelineEdge).filter(PipelineEdge.rule_id == rule.id).all()
    assert len(edges) == 3
    true_edges = [e for e in edges if e.source_port == "true"]
    assert len(true_edges) == 1
    assert true_edges[0].target_step_id == steps["end"].id


def test_meal_open_uses_scene_description_condition_not_detection_labels(
    imported_rules, db_session
):
    # DL-M04 deviation: the deployed YOLO detector is person-only (verified
    # against scene-analysis-service's decode_output), so this rule confirms
    # via a Florence-2 caption keyword check, not a detection-label match.
    rule = imported_rules["daily_living_meal_open"]
    steps = {
        s.label: s
        for s in db_session.query(PipelineStep).filter(PipelineStep.rule_id == rule.id).all()
    }
    assert set(steps) == {"poll", "scene", "should_open", "start"}
    assert steps["poll"].step_type == "media_window_poll"
    assert steps["scene"].step_type == "scene_analysis"
    assert steps["scene"].config_json["run_detect"] is False
    expression = steps["should_open"].config_json["expression"]
    assert "steps.scene.outputs.scene_description" in expression
    assert steps["start"].config_json["activity_type"] == "meal_eating"
    assert steps["start"].config_json["confidence"] == 0.6

    contexts = db_session.query(RuleContext).filter(RuleContext.rule_id == rule.id).all()
    assert {c.context_type for c in contexts} == {
        "time_range",
        "presence_status",
        "presence_dwell",
    }


def test_meal_close_chain(imported_rules, db_session):
    rule = imported_rules["daily_living_meal_close"]
    steps = {
        s.label: s
        for s in db_session.query(PipelineStep).filter(PipelineStep.rule_id == rule.id).all()
    }
    assert set(steps) == {"presence", "should_close", "end"}
    assert steps["end"].config_json["activity_type"] == "meal_eating"
