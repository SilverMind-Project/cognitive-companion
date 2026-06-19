"""Tests for the completion_gate vision-shape normalizer (VG05 + VG08)."""

from __future__ import annotations

from backend.schemas.guided_task import RoutineStepIn


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
                "watch": {"enabled": True, "tick_s": 15, "auto_advance": False, "auto_advance_k": 2},
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
