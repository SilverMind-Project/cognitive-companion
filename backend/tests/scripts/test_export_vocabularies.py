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


def test_export_includes_tea_intent_suspected():
    vocabularies = build_vocabularies()
    assert "tea_intent_suspected" in vocabularies["signal_kinds"]


def test_export_includes_hygiene_routine_missed():
    vocabularies = build_vocabularies()
    assert "hygiene_routine_missed" in vocabularies["signal_kinds"]


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


def test_export_lists_every_mcp_tool_with_its_token():
    from backend.mcp.server import _tool_handlers

    vocabularies = build_vocabularies()
    # Non-vacuity: an empty registry would make the docs-site count check meaningless.
    assert len(vocabularies["mcp_tools"]) > 40
    assert vocabularies["mcp_tools"] == sorted(_tool_handlers)
    assert set(vocabularies["mcp_tool_tokens"]) == set(vocabularies["mcp_tools"])
    assert all(token for token in vocabularies["mcp_tool_tokens"].values())


def test_export_wire_signal_kinds_are_the_cts_subset():
    vocabularies = build_vocabularies()
    wire = set(vocabularies["wire_signal_kinds"])
    assert wire, "expected the CTS wire vocabulary"
    assert wire < set(vocabularies["signal_kinds"])
    assert "tea_intent_suspected" not in wire
