"""Tests for the completion_gate vision-shape normalizer (VG05 + VG08)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.guided_task import RoutineStepIn
from backend.services.guided_task.routine_admin import sanitize_completion_gate


def _normalize(completion_gate: dict) -> dict:
    step = RoutineStepIn(ord=0, prompt_template="do the thing", completion_gate=completion_gate)
    return step.completion_gate


def test_new_vision_shape_round_trips_including_max_disagreements() -> None:
    out = _normalize(
        {
            "kinds": ["response", "vision_confirm"],
            "vision": {
                "gate_graph_rule_id": 42,
                "preset_key": "kettle_on_hob",
                "confirm": {
                    "window_s": 25,
                    "max_frames": 6,
                    "min_confidence": 0.8,
                    "min_interval_s": 10,
                    "max_disagreements": 4,
                    "on_max_disagreements": "escalate",
                    "model_id": None,
                },
                "watch": {
                    "enabled": True,
                    "tick_s": 15,
                    "auto_advance": False,
                    "auto_advance_k": 2,
                },
            },
        }
    )
    vision = out["vision"]
    assert vision["gate_graph_rule_id"] == 42
    # preset_key (editor-only display hint) is preserved.
    assert vision["preset_key"] == "kettle_on_hob"
    # max_disagreements is a real per-step override the runtime reads; it must persist.
    assert vision["confirm"]["max_disagreements"] == 4
    assert vision["confirm"]["on_max_disagreements"] == "escalate"
    assert vision["watch"]["enabled"] is True


def test_legacy_vision_keys_are_stripped() -> None:
    out = _normalize(
        {
            "kinds": ["vision_confirm"],
            "vision": {
                "gate_graph_rule_id": 7,
                "camera_ids": ["cam1"],  # dead override (D25)
                "description": "what done looks like",  # superseded by preset + canvas
            },
        }
    )
    assert "camera_ids" not in out["vision"]
    assert "description" not in out["vision"]
    assert out["vision"]["gate_graph_rule_id"] == 7


def test_routine_admin_sanitize_completion_gate_matches_schema_validator() -> None:
    gate = {
        "kinds": ["response", "vision_confirm"],
        "vision": {
            "gate_graph_rule_id": 11,
            "confirm": {
                "window_s": 20,
                "max_frames": 4,
                "max_cameras": 2,
                "min_confidence": 0.75,
                "min_interval_s": 5,
                "model_id": "gemma-4-26B-A4B-it",
                "max_disagreements": 3,
                "on_max_disagreements": "escalate",
            },
            "watch": {
                "enabled": True,
                "tick_s": 10,
                "window_s": 15,
                "max_frames": 3,
                "max_cameras": 1,
                "min_confidence": 0.85,
                "model_id": None,
                "auto_advance": True,
                "auto_advance_k": 2,
            },
        },
    }
    via_schema = _normalize(gate)
    via_service = sanitize_completion_gate(gate)
    assert via_schema == via_service
    assert via_service["vision"]["confirm"]["max_disagreements"] == 3
    assert via_service["vision"]["confirm"]["max_cameras"] == 2
    assert via_service["vision"]["watch"]["max_cameras"] == 1
    assert via_service["vision"]["watch"]["min_confidence"] == 0.85


def test_profile_overrides_survive_save_and_runtime_parse() -> None:
    """Every per-profile override a caregiver saves must reach the runtime model.

    The sanitizer kept these keys, but the runtime's Pydantic profile models
    ignored unknown fields, so ``max_cameras`` and the watch ``min_confidence``
    were saved and then silently dropped on every evaluation.
    """
    from backend.services.guided_task.domain import CompletionGateConfig

    gate = {
        "kinds": ["response", "vision_confirm"],
        "vision": {
            "gate_graph_rule_id": 42,
            "confirm": {"max_disagreements": 3, "max_cameras": 2},
            "watch": {"enabled": True, "max_cameras": 1, "min_confidence": 0.85},
        },
    }
    saved = sanitize_completion_gate(_normalize(gate))
    parsed = CompletionGateConfig.model_validate(saved).vision
    assert parsed is not None
    assert parsed.confirm is not None
    assert parsed.watch is not None
    assert parsed.confirm.max_disagreements == 3
    assert parsed.confirm.max_cameras == 2
    assert parsed.watch.max_cameras == 1
    assert parsed.watch.min_confidence == 0.85


# ---------------------------------------------------------------------------
# Activity and zone sub-configs, and skip conditions: only the shapes the
# runtime evaluates are accepted.
# ---------------------------------------------------------------------------


def test_activity_gate_is_canonical_and_legacy_seconds_convert() -> None:
    out = _normalize(
        {
            "kinds": ["response", "activity_signal"],
            "activity": {"activity_type": "cooking", "window_s": 300},
        }
    )

    assert out["activity"] == {"activity_type": "cooking", "window_minutes": 5.0}


def test_activity_gate_defaults_its_window() -> None:
    out = _normalize({"kinds": ["activity_signal"], "activity": {"activity_type": "medication"}})

    assert out["activity"]["window_minutes"] == 10


@pytest.mark.parametrize(
    "activity",
    [None, {"activity_type": "pour_liquid"}, {"activity_type": "cooking", "window_minutes": 0}],
)
def test_activity_gate_rejects_what_could_never_match(activity) -> None:
    gate: dict = {"kinds": ["activity_signal"]}
    if activity is not None:
        gate["activity"] = activity
    with pytest.raises(ValidationError):
        _normalize(gate)


def test_unticked_activity_config_is_dropped() -> None:
    out = _normalize({"kinds": ["response"], "activity": {"activity_type": ""}})

    assert "activity" not in out


def test_legacy_zone_key_becomes_the_key_the_evaluator_reads() -> None:
    out = _normalize({"kinds": ["zone_presence"], "zone": {"zone_id": 4}})

    assert out["zone_presence"] == {"zone_id": 4}
    assert "zone" not in out


def _step(skip_condition):
    return RoutineStepIn(ord=0, prompt_template="do the thing", skip_condition=skip_condition)


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ({"kind": "response_says_done"}, {"kind": "response_says_done"}),
        (
            {"kind": "activity_signal", "activity_type": "cooking", "window_minutes": 5},
            {"kind": "activity_signal", "activity_type": "cooking", "window_minutes": 5.0},
        ),
        ({"kind": "zone_presence", "zone_id": 3}, {"kind": "zone_presence", "zone_id": 3}),
        ({"kind": "zone_presence"}, {"kind": "zone_presence", "zone_id": None}),
    ],
)
def test_valid_skip_conditions_round_trip(given, stored) -> None:
    assert _step(given).model_dump(mode="json")["skip_condition"] == stored


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "already_done"},
        {"kind": "activity_signal", "signal_kind": "kettle_boiled", "within_s": 300},
        {"kind": "activity_signal", "activity_type": "pour_liquid"},
        {"kind": "response_says_done", "extra": 1},
    ],
)
def test_skip_conditions_the_runtime_cannot_evaluate_are_rejected(bad) -> None:
    with pytest.raises(ValidationError):
        _step(bad)
