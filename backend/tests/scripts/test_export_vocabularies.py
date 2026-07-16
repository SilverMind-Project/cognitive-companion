from __future__ import annotations

import json

from backend.scripts.export_vocabularies import build_vocabularies


def test_export_is_deterministic():
    first = json.dumps(build_vocabularies(), indent=2, sort_keys=True)
    second = json.dumps(build_vocabularies(), indent=2, sort_keys=True)
    assert first == second


def test_export_includes_gait_slowing():
    vocabularies = build_vocabularies()
    assert "gait_slowing" in vocabularies["signal_kinds"]


def test_export_step_types_have_expected_shape():
    vocabularies = build_vocabularies()
    assert vocabularies["step_types"], "expected at least one registered step type"
    for step in vocabularies["step_types"]:
        assert set(step) == {
            "type_name",
            "display_name",
            "icon",
            "category",
            "output_ports",
            "gate_safe",
        }
