"""DL-M08 Part D/E.6: the hygiene-confirm rule bundle imports cleanly with the
expected trigger, filter, steps, and edges.
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

_BUNDLE_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "rule_bundles"
    / "daily_living_hygiene_confirm.json"
)

_PLACEHOLDERS = {"__BATHROOM_ROOM_NAME__": "bathroom"}


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
    rule = db_session.get(Rule, report.rule_id)
    assert rule is not None
    return rule


def test_rule_triggers_on_dementia_signal_and_is_enabled(imported_rule):
    assert imported_rule.enabled is True
    assert imported_rule.trigger_types == ["dementia_signal"]


def test_rule_has_no_daily_trigger_or_cooloff_limit(imported_rule):
    # Rate limiting in RulesEngine._check_rate_limits is scoped by rule_id
    # only (no person_id), so a nonzero cool-off/daily-cap here would drop a
    # second resident's same_clothes_suspected signal arriving soon after the
    # first's in a multi-resident household. CTS already dedupes to at most
    # one signal per identity per local day, and signal_emit's
    # dedupe_minutes=1200 is scoped per-kind-per-person downstream.
    assert imported_rule.cool_off_minutes == 0
    assert imported_rule.max_daily_triggers == 0


def test_rule_has_dementia_signal_filter_scoped_to_same_clothes_suspected(
    imported_rule, db_session
):
    contexts = db_session.query(RuleContext).filter(RuleContext.rule_id == imported_rule.id).all()
    assert len(contexts) == 1
    assert contexts[0].context_type == "dementia_signal"
    assert contexts[0].config_json["kinds"] == ["same_clothes_suspected"]


def test_rule_has_expected_steps(imported_rule, db_session):
    steps = {
        s.label: s
        for s in db_session.query(PipelineStep).filter(PipelineStep.rule_id == imported_rule.id).all()
    }
    assert set(steps) == {
        "media_presign_1",
        "vlm_compare",
        "same_outfit_check",
        "bathroom_dwell",
        "no_dwell_check",
        "emit_hygiene_signal",
        "alert_missed_hygiene",
        "alert_washed_up",
    }
    assert steps["media_presign_1"].step_type == "media_presign"
    assert steps["vlm_compare"].step_type == "llm_call"
    assert steps["same_outfit_check"].step_type == "condition"
    assert steps["bathroom_dwell"].step_type == "presence_query"
    assert steps["bathroom_dwell"].config_json["query_mode"] == "room_dwell_history"
    assert steps["no_dwell_check"].step_type == "condition"
    assert steps["emit_hygiene_signal"].step_type == "signal_emit"
    assert steps["emit_hygiene_signal"].config_json["kind"] == "hygiene_routine_missed"
    assert steps["alert_missed_hygiene"].step_type == "notification"
    assert steps["alert_washed_up"].step_type == "notification"
    # Ships enabled; the step's own enabled flag is the "rule config the
    # owner can disable" the milestone calls for (Part D step 7), no
    # separate mechanism needed.
    assert steps["alert_washed_up"].enabled is True


def test_rule_wires_both_branches_of_no_dwell_check(imported_rule, db_session):
    steps = {
        s.label: s
        for s in db_session.query(PipelineStep).filter(PipelineStep.rule_id == imported_rule.id).all()
    }
    edges = db_session.query(PipelineEdge).filter(PipelineEdge.rule_id == imported_rule.id).all()

    no_dwell_check = steps["no_dwell_check"]
    true_targets = {
        e.target_step_id for e in edges if e.source_step_id == no_dwell_check.id and e.source_port == "true"
    }
    false_targets = {
        e.target_step_id for e in edges if e.source_step_id == no_dwell_check.id and e.source_port == "false"
    }
    assert true_targets == {steps["emit_hygiene_signal"].id, steps["alert_missed_hygiene"].id}
    assert false_targets == {steps["alert_washed_up"].id}


def test_same_outfit_check_false_branch_has_no_outgoing_edge(imported_rule, db_session):
    """VLM-disagree branch: the rule ends with no notification (Part D step 8)."""
    steps = {
        s.label: s
        for s in db_session.query(PipelineStep).filter(PipelineStep.rule_id == imported_rule.id).all()
    }
    edges = db_session.query(PipelineEdge).filter(PipelineEdge.rule_id == imported_rule.id).all()
    same_outfit_check = steps["same_outfit_check"]
    false_edges = [
        e for e in edges if e.source_step_id == same_outfit_check.id and e.source_port == "false"
    ]
    assert false_edges == []
