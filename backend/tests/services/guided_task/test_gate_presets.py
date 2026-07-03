from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from backend.models.pipeline import PipelineEdge, PipelineStep
from backend.services.guided_task.camera_selection import ResolvedCamera
from backend.services.guided_task.gate_presets import (
    GATE_PRESETS,
    build_default_vlm_gate,
    build_kettle_on_hob_gate,
    seed_presets,
)
from backend.services.guided_task.gate_runner import GateGraphRunner, GateProfile, GateRunContext
from backend.services.pipeline_graph import validate_gate_graph
from backend.steps import StepRegistry
from backend.steps.base import ServiceContainer


class MockSettings:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def as_str(self, key: str, default: Any = None) -> str:
        return self._values.get(key, default)

    def as_float(self, key: str, default: Any = None) -> float:
        val = self._values.get(key, default)
        return float(val) if val is not None else None

    def as_bool(self, key: str, default: Any = None) -> bool:
        return bool(self._values.get(key, default))


class MockLLMModelConfig:
    def __init__(self, capabilities: list[str] | None = None) -> None:
        self.capabilities = capabilities or ["text", "vision"]


class MockLLMRegistry:
    def __init__(self, provider: Any, capabilities: list[str] | None = None) -> None:
        self.provider = provider
        self.config = MockLLMModelConfig(capabilities)

    def get_provider(self, model_id: str) -> Any:
        return self.provider

    def get_config(self, model_id: str) -> Any:
        return self.config


class MockLLMProvider:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def call(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return self.response


class MockBucketizer:
    def buffer_stats(self) -> dict[str, int]:
        return {"cam1": 1}

    def forward_buffer(
        self, window_id: str, camera_id: str, lookahead_s: float, eligible_only: bool = False
    ) -> list[dict[str, Any]]:
        return []


def test_build_default_vlm_gate_is_valid(db_session: Session) -> None:
    # 1. Build default VLM gate rule
    rule = build_default_vlm_gate(
        db_session,
        name="Test Default VLM Gate",
        done_description="person is standing at the sink",
    )

    # 2. Query steps and edges
    steps = db_session.query(PipelineStep).filter(PipelineStep.rule_id == rule.id).all()
    edges = db_session.query(PipelineEdge).filter(PipelineEdge.rule_id == rule.id).all()

    # 3. Validate
    StepRegistry.discover()

    def get_meta(step_type: str):
        handler = StepRegistry.get(step_type)
        return handler.metadata() if handler else None

    errors = validate_gate_graph(steps, edges, step_metadata=get_meta, gate_safe_only=False)
    assert len(errors) == 0, f"Expected no validation errors, got {errors}"


@pytest.mark.asyncio
async def test_default_gate_runs_to_verdict(db_session: Session) -> None:
    # 1. Build default VLM gate rule
    rule = build_default_vlm_gate(
        db_session,
        name="Test Runs to Verdict",
        done_description="resident completed routine step",
    )

    # 2. Setup runner with mock services
    llm_provider = MockLLMProvider('{"complete": true, "confidence": 0.85, "reason": "success"}')
    llm_registry = MockLLMRegistry(llm_provider)

    services = ServiceContainer(
        db_factory=lambda: db_session,
        bucketizer=MockBucketizer(),
        minio_client=MagicMock(),
        event_aggregator=MagicMock(),
        llm_model_registry=llm_registry,
        scene_analysis_client=MagicMock(),
    )

    test_settings = MockSettings(
        {
            "app.timezone": "UTC",
            "guided_task.vision.gate_node_timeout_s": 5.0,
            "guided_task.vision.confirm.min_confidence": 0.7,
        }
    )

    runner = GateGraphRunner(
        services=services,
        db_factory=lambda: db_session,
        settings=test_settings,
    )

    profile = GateProfile(
        name="confirm",
        window_s=20.0,
        max_frames=9,
        min_confidence=0.7,
        model_id="mock-model",
    )
    context = GateRunContext(
        person_id="p1",
        room_name="Living Room",
        sensor_id="s1",
        session_id="sess1",
        step_ord=1,
    )

    from backend.services.guided_task.camera_selection import ResolvedCamera

    cameras = [ResolvedCamera(id="cam1", source="cts")]

    # Run
    verdict = await runner.run(
        gate_rule_id=rule.id,
        profile=profile,
        cameras=cameras,
        context=context,
    )

    assert verdict.complete is True
    assert verdict.confidence == 0.85
    assert verdict.reason == "success"


@pytest.mark.asyncio
async def test_preset_threshold_is_profile_inherited_end_to_end(db_session: Session) -> None:
    """End-to-end proof that the preset's fail-closed threshold is the
    profile-inherited ``min_confidence`` (the preset no longer hardcodes it).

    The VLM returns confidence 0.85; a strict profile threshold of 0.95 must fail the
    verdict closed. This exercises the load-bearing F2 injection path
    (``GateGraphRunner`` -> ``pipeline_data["_profile"]`` -> ``gate_verdict``) that a
    unit test on a fake step cannot reach. The complementary "completes when threshold
    is below the score" direction is covered by ``test_default_gate_runs_to_verdict``
    (profile 0.7, confidence 0.85 -> complete). Each test runs a single gate so the
    shared ``db_session`` (which ``runner.run`` closes via its ``with`` block) stays
    valid; the real app's ``db_factory`` opens a fresh session per run.
    """
    rule = build_default_vlm_gate(db_session, name="Test Profile Threshold")

    llm_provider = MockLLMProvider('{"complete": true, "confidence": 0.85, "reason": "ok"}')
    services = ServiceContainer(
        db_factory=lambda: db_session,
        bucketizer=MockBucketizer(),
        minio_client=MagicMock(),
        event_aggregator=MagicMock(),
        llm_model_registry=MockLLMRegistry(llm_provider),
        scene_analysis_client=MagicMock(),
    )
    test_settings = MockSettings(
        {
            "app.timezone": "UTC",
            "guided_task.vision.gate_node_timeout_s": 5.0,
            "guided_task.vision.confirm.min_confidence": 0.7,
        }
    )
    runner = GateGraphRunner(
        services=services, db_factory=lambda: db_session, settings=test_settings
    )
    context = GateRunContext(
        person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1
    )
    cameras = [ResolvedCamera(id="cam1", source="cts")]

    # Strict threshold above the VLM's 0.85 -> inherited min_confidence fails it closed.
    strict = GateProfile(
        name="confirm", window_s=20.0, max_frames=9, min_confidence=0.95, model_id="mock-model"
    )
    verdict = await runner.run(
        gate_rule_id=rule.id, profile=strict, cameras=cameras, context=context
    )
    assert verdict.complete is False
    assert verdict.reason == "low_confidence"


def _gate_meta_fn():
    StepRegistry.discover()

    def get_meta(step_type: str):
        handler = StepRegistry.get(step_type)
        return handler.metadata() if handler else None

    return get_meta


def test_each_seeded_preset_passes_validate_gate_graph(db_session: Session) -> None:
    seeded = seed_presets(db_session)
    assert len(seeded) == len(GATE_PRESETS)

    from backend.services.template_validator import validate_step_config

    get_meta = _gate_meta_fn()
    for rule in seeded:
        steps = db_session.query(PipelineStep).filter(PipelineStep.rule_id == rule.id).all()
        edges = db_session.query(PipelineEdge).filter(PipelineEdge.rule_id == rule.id).all()
        errors = validate_gate_graph(steps, edges, step_metadata=get_meta, gate_safe_only=False)
        assert errors == [], f"preset '{rule.name}' failed validation: {errors}"

        # The router's /validate also lints every template expression. Seeded
        # presets are shipped content, so their condition/verdict expressions
        # must lint clean (this is what a caregiver hits clicking "Validate").
        known_labels = [s.label for s in steps]
        for step in steps:
            tmpl_errors = validate_step_config(step.step_type, step.config_json or {}, known_labels)
            assert tmpl_errors == [], (
                f"preset '{rule.name}' step '{step.label}' has template errors: {tmpl_errors}"
            )


def test_seed_presets_is_idempotent(db_session: Session) -> None:
    first = seed_presets(db_session)
    second = seed_presets(db_session)
    assert [r.id for r in first] == [r.id for r in second]
    # No duplicate rules created on the second run.
    from backend.models.rule import Rule

    for preset in GATE_PRESETS:
        count = db_session.query(Rule).filter(Rule.name == preset.name).count()
        assert count == 1


@pytest.mark.asyncio
async def test_kettle_preset_cheap_exit_when_no_detection(db_session: Session) -> None:
    """When scene_analysis finds no kettle, the condition routes to the cheap
    exit and the heavy VLM is never invoked (the join still fires the verdict)."""
    rule = build_kettle_on_hob_gate(db_session, name="Kettle Cheap Exit Test")

    llm_provider = MockLLMProvider(
        '{"complete": true, "confidence": 0.9, "reason": "kettle on hob"}'
    )
    llm_registry = MockLLMRegistry(llm_provider)

    services = ServiceContainer(
        db_factory=lambda: db_session,
        bucketizer=MockBucketizer(),
        minio_client=MagicMock(),
        event_aggregator=MagicMock(),
        llm_model_registry=llm_registry,
        # scene_analysis_client left None -> scene step returns empty detections,
        # so the kettle condition is False and routes to the cheap exit.
        scene_analysis_client=None,
    )

    test_settings = MockSettings(
        {
            "app.timezone": "UTC",
            "guided_task.vision.gate_node_timeout_s": 5.0,
            "guided_task.vision.confirm.min_confidence": 0.7,
        }
    )

    runner = GateGraphRunner(
        services=services,
        db_factory=lambda: db_session,
        settings=test_settings,
    )

    profile = GateProfile(
        name="confirm", window_s=20.0, max_frames=9, min_confidence=0.7, model_id="mock-model"
    )
    context = GateRunContext(
        person_id="p1", room_name="Kitchen", sensor_id="s1", session_id="sess1", step_ord=1
    )

    from backend.services.guided_task.camera_selection import ResolvedCamera

    cameras = [ResolvedCamera(id="cam1", source="cts")]

    verdict = await runner.run(
        gate_rule_id=rule.id, profile=profile, cameras=cameras, context=context
    )

    assert llm_provider.calls == [], "heavy VLM must not be called on the cheap exit"
    assert verdict.complete is False
