"""Tests for validate_gate_graph function."""

from __future__ import annotations

from dataclasses import dataclass

from backend.services.pipeline_graph import validate_gate_graph
from backend.steps.base import StepMetadata


@dataclass
class _FakeStep:
    id: int
    step_type: str


@dataclass
class _FakeEdge:
    source_step_id: int
    source_port: str
    target_step_id: int
    target_port: str


def _mock_metadata(step_type: str) -> StepMetadata | None:
    # Safe step types
    if step_type == "media_window_poll":
        return StepMetadata(
            type_name="media_window_poll",
            display_name="Poll Media Window",
            category="perception",
            icon="",
            description="",
            config_schema={},
            default_config={},
            gate_safe=True,
        )
    elif step_type == "gate_verdict":
        return StepMetadata(
            type_name="gate_verdict",
            display_name="Gate Verdict",
            category="flow",
            icon="",
            description="",
            config_schema={},
            default_config={},
            gate_safe=True,
            gate_only=True,
        )
    elif step_type == "condition":
        return StepMetadata(
            type_name="condition",
            display_name="Condition",
            category="reasoning",
            icon="",
            description="",
            config_schema={},
            default_config={},
            gate_safe=True,
            output_ports=("true", "false"),
        )
    # Unsafe step types
    elif step_type == "notification":
        return StepMetadata(
            type_name="notification",
            display_name="Notification",
            category="action",
            icon="",
            description="",
            config_schema={},
            default_config={},
            gate_safe=False,
        )
    return None


def test_rejects_non_gate_safe_step():
    steps = [
        _FakeStep(id=1, step_type="media_window_poll"),
        _FakeStep(id=2, step_type="notification"),
        _FakeStep(id=3, step_type="gate_verdict"),
    ]
    edges = [
        _FakeEdge(source_step_id=1, source_port="main", target_step_id=2, target_port="main"),
        _FakeEdge(source_step_id=2, source_port="main", target_step_id=3, target_port="main"),
    ]
    errors = validate_gate_graph(steps, edges, step_metadata=_mock_metadata)
    assert any("non-gate-safe step types" in err for err in errors)
    assert any("notification" in err for err in errors)


def test_rejects_when_no_gate_verdict():
    steps = [
        _FakeStep(id=1, step_type="media_window_poll"),
    ]
    edges = []
    errors = validate_gate_graph(steps, edges, step_metadata=_mock_metadata)
    assert any("must contain exactly one gate_verdict step" in err for err in errors)


def test_rejects_when_multiple_gate_verdicts():
    steps = [
        _FakeStep(id=1, step_type="media_window_poll"),
        _FakeStep(id=2, step_type="gate_verdict"),
        _FakeStep(id=3, step_type="gate_verdict"),
    ]
    edges = [
        _FakeEdge(source_step_id=1, source_port="main", target_step_id=2, target_port="main"),
        # step 3 is not wired or wired, but multiple verdicts is a rejection
    ]
    errors = validate_gate_graph(steps, edges, step_metadata=_mock_metadata)
    assert any("must contain exactly one gate_verdict step; found 2" in err for err in errors)


def test_rejects_when_gate_verdict_unreachable():
    steps = [
        _FakeStep(id=1, step_type="media_window_poll"),
        _FakeStep(id=2, step_type="gate_verdict"),
    ]
    # No edges -> verdict unreachable from entry (poll) step
    edges = []
    errors = validate_gate_graph(steps, edges, step_metadata=_mock_metadata)
    assert len(errors) > 0

    # Test cycle-based unreachable verdict (exactly one entry step 1, but step 3 verdict unreachable due to cycle)
    steps_cycle = [
        _FakeStep(id=1, step_type="media_window_poll"),
        _FakeStep(id=3, step_type="gate_verdict"),
    ]
    edges_cycle = [
        _FakeEdge(source_step_id=3, source_port="main", target_step_id=3, target_port="main"),
    ]
    errors_cycle = validate_gate_graph(steps_cycle, edges_cycle, step_metadata=_mock_metadata)
    assert any("is not reachable from the entry node" in err for err in errors_cycle)


def test_accepts_minimal_valid_gate():
    steps = [
        _FakeStep(id=1, step_type="media_window_poll"),
        _FakeStep(id=2, step_type="gate_verdict"),
    ]
    edges = [
        _FakeEdge(source_step_id=1, source_port="main", target_step_id=2, target_port="main"),
    ]
    errors = validate_gate_graph(steps, edges, step_metadata=_mock_metadata)
    assert len(errors) == 0


def test_accepts_branchy_valid_gate():
    steps = [
        _FakeStep(id=1, step_type="media_window_poll"),
        _FakeStep(id=2, step_type="condition"),
        _FakeStep(id=3, step_type="gate_verdict"),
    ]
    # Condition branches true and false, both lead to the same verdict step 3
    edges = [
        _FakeEdge(source_step_id=1, source_port="main", target_step_id=2, target_port="main"),
        _FakeEdge(source_step_id=2, source_port="true", target_step_id=3, target_port="main"),
        _FakeEdge(source_step_id=2, source_port="false", target_step_id=3, target_port="main"),
    ]
    errors = validate_gate_graph(steps, edges, step_metadata=_mock_metadata)
    assert len(errors) == 0


def test_edit_time_allows_missing_verdict():
    steps = [
        _FakeStep(id=1, step_type="media_window_poll"),
    ]
    edges = []
    # If gate_safe_only=True, missing verdict is allowed (no errors)
    errors = validate_gate_graph(steps, edges, step_metadata=_mock_metadata, gate_safe_only=True)
    assert len(errors) == 0
