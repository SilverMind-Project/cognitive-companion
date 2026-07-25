"""DL-M06: the tea-intent shadow-detector rule bundle imports cleanly onto a
fresh DB with the expected trigger, filters, step chain, and edges -- and,
critically, without a guided_task_start step (the shadow-mode guard: this
bundle must never autonomously launch a session)."""

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

_BUNDLE_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "rule_bundles" / "daily_living_tea_intent_shadow.json"
)

_PLACEHOLDERS = {
    "__RESIDENT_PERSON_ID__": "test_resident",
    "__KITCHEN_ROOM_NAME__": "kitchen",
    "__KITCHEN_CAMERA_SENSOR_ID__": "test_kitchen_cam",
}


def _load_bundle() -> RuleBundle:
    raw = _BUNDLE_PATH.read_text()
    for placeholder, value in _PLACEHOLDERS.items():
        raw = raw.replace(placeholder, value)
    return RuleBundle(**json.loads(raw))


@pytest.fixture
def imported_rule(db_session) -> Rule:
    bundle = _load_bundle()
    report = bundle_to_rule(bundle, db_session, app_version="test")
    assert report.status == "ok", report.errors
    db_session.commit()
    return db_session.get(Rule, report.rule_id)


def test_imports_as_enabled_cron_rule(imported_rule):
    assert imported_rule.enabled is True
    assert imported_rule.trigger_types == ["cron"]


def test_rate_limit_is_the_cool_off_not_a_daily_cap(imported_rule):
    # DL-M06: the rule's own cool_off_minutes is the "one intent evaluation
    # per window" limiter (armed only by signal_emit's trigger_cooloff on a
    # real positive detection); max_daily_triggers stays unbounded so a
    # negative-verdict poll never counts against it.
    assert imported_rule.cool_off_minutes == 45
    assert imported_rule.max_daily_triggers == 0


def test_contexts_are_time_range_and_presence_dwell(imported_rule, db_session):
    contexts = db_session.query(RuleContext).filter(RuleContext.rule_id == imported_rule.id).all()
    context_types = {c.context_type for c in contexts}
    assert context_types == {"time_range", "presence_dwell"}

    dwell_ctx = next(c for c in contexts if c.context_type == "presence_dwell")
    assert dwell_ctx.config_json["person_id"] == "test_resident"
    assert dwell_ctx.config_json["min_minutes"] == 3


def test_step_chain_matches_the_cheap_first_cascade(imported_rule, db_session):
    steps = {
        s.label: s
        for s in db_session.query(PipelineStep).filter(PipelineStep.rule_id == imported_rule.id).all()
    }
    assert set(steps) == {
        "poll",
        "scene",
        "region_presence_1",
        "in_region_check",
        "tea_verdict",
        "verdict_check",
        "emit_signal",
        "notify_caregiver",
    }
    assert steps["poll"].step_type == "media_window_poll"
    assert steps["scene"].step_type == "scene_analysis"
    assert steps["region_presence_1"].step_type == "region_presence"
    assert steps["in_region_check"].step_type == "condition"
    assert steps["tea_verdict"].step_type == "llm_call"
    assert steps["verdict_check"].step_type == "condition"
    assert steps["emit_signal"].step_type == "signal_emit"
    assert steps["notify_caregiver"].step_type == "notification"


def test_no_tier4_vlm_call_by_default(imported_rule, db_session):
    # DL5: the default cascade is text-only reasoning (tier 3), never the
    # vLLM VLM (tier 4), even though model_id is config an owner could swap.
    steps = {
        s.label: s
        for s in db_session.query(PipelineStep).filter(PipelineStep.rule_id == imported_rule.id).all()
    }
    assert steps["tea_verdict"].config_json["image_source"] == "none"


def test_signal_emit_config_uses_the_cc_local_kind_and_dedupe(imported_rule, db_session):
    steps = {
        s.label: s
        for s in db_session.query(PipelineStep).filter(PipelineStep.rule_id == imported_rule.id).all()
    }
    emit_config = steps["emit_signal"].config_json
    assert emit_config["kind"] == "tea_intent_suspected"
    assert emit_config["person_id"] == "test_resident"
    # dedupe_minutes must be 0 here: the rule's own cool_off_minutes=45 already
    # blocks re-entry into the whole cascade for 45 minutes after a completed
    # run, so a nonzero step-local dedupe on top of it only fires on the rare
    # cool-off-expired-but-still-unacknowledged edge -- and when it does, it
    # suppresses the write without setting _cooloff_triggered, which leaves the
    # cool-off DISARMED and the rule re-fires (and re-runs the full vision
    # cascade) every 2 minutes until the caregiver acks or 60 minutes pass. Two
    # rate limiters stacked on one rule is exactly what the engineering
    # standards skill's DL-M06 section says not to do.
    assert emit_config["dedupe_minutes"] == 0
    assert emit_config["trigger_cooloff"] is True


def test_verdict_check_gates_both_signal_and_notification(imported_rule, db_session):
    steps = {
        s.label: s
        for s in db_session.query(PipelineStep).filter(PipelineStep.rule_id == imported_rule.id).all()
    }
    edges = db_session.query(PipelineEdge).filter(PipelineEdge.rule_id == imported_rule.id).all()
    verdict_edges = [
        e for e in edges if e.source_step_id == steps["verdict_check"].id and e.source_port == "true"
    ]
    targets = {e.target_step_id for e in verdict_edges}
    assert targets == {steps["emit_signal"].id, steps["notify_caregiver"].id}


def test_bundle_never_includes_guided_task_start(imported_rule, db_session):
    # The shadow-mode guard: this bundle must not be able to autonomously
    # launch a guided session. The flip (DL-M06 Part D) is a separate,
    # explicit config edit executed later, gated on hardening + precision.
    steps = db_session.query(PipelineStep).filter(PipelineStep.rule_id == imported_rule.id).all()
    assert all(s.step_type != "guided_task_start" for s in steps)
