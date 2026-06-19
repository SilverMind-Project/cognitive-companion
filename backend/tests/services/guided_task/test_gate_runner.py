"""Tests for GateGraphRunner."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from backend.integrations.scene_analysis_client import SceneAnalyzeResult, SceneDetection
from backend.models.pipeline import PipelineEdge, PipelineStep, WorkflowExecution
from backend.models.rule import Rule
from backend.services.guided_task.camera_selection import ResolvedCamera
from backend.services.guided_task.gate_runner import (
    GateGraphRunner,
    GateProfile,
    GateRunContext,
    GateVerdict,
    _CoolOffCache,
)
from backend.steps import StepRegistry
from backend.steps.base import ServiceContainer, StepResult


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
    def __init__(self) -> None:
        self.stats = {"cam1": 1}

    def buffer_stats(self) -> dict[str, int]:
        return self.stats

    def forward_buffer(self, window_id: str, camera_id: str, lookahead_s: float, eligible_only: bool = False) -> list[dict[str, Any]]:
        return [
            {
                "camera_id": camera_id,
                "event_time": datetime.now(UTC).isoformat(),
                "detections": [],
                "minio_key": "frames/cam1.jpg",
                "image_eligible": True,
            }
        ]


class MockMinio:
    def generate_presigned_url(self, object_name: str, expiration: int = 3600) -> str:
        return f"https://minio/{object_name}"


class MockEventAggregator:
    def __init__(self, images: list[dict[str, Any]] | None = None) -> None:
        self.images = images or []
        self.queries: list[dict[str, Any]] = []

    async def query_media_by_sensor(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.queries.append(kwargs)
        return self.images

    async def query_recent_media(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.queries.append(kwargs)
        return self.images


class MockSceneAnalysisClient:
    def __init__(self, result: SceneAnalyzeResult | None = None) -> None:
        self.configured = True
        self.result = result or SceneAnalyzeResult()
        self.calls: list[Any] = []

    async def analyze(self, *args: Any, **kwargs: Any) -> SceneAnalyzeResult:
        self.calls.append((args, kwargs))
        return self.result


def _make_rule(db: Session, name: str = "Test Gate Rule", enabled: bool = True) -> Rule:
    rule = Rule(name=name, enabled=enabled, trigger_types=[])
    db.add(rule)
    db.flush()
    return rule


def _make_step(db: Session, rule: Rule, order: int, step_type: str, config: dict[str, Any] | None = None, enabled: bool = True, label: str | None = None) -> PipelineStep:
    if label is None:
        label = f"{step_type}_{order}"
    step = PipelineStep(
        rule_id=rule.id,
        order=order,
        step_type=step_type,
        label=label,
        config_json=config or {},
        enabled=enabled,
    )
    db.add(step)
    db.flush()
    return step


def _connect(db: Session, rule: Rule, source: PipelineStep, target: PipelineStep, source_port: str = "main") -> PipelineEdge:
    edge = PipelineEdge(
        rule_id=rule.id,
        source_step_id=source.id,
        source_port=source_port,
        target_step_id=target.id,
        target_port="main",
    )
    db.add(edge)
    db.flush()
    return edge


@pytest.fixture
def test_settings() -> MockSettings:
    return MockSettings({
        "app.timezone": "UTC",
        "guided_task.vision.gate_node_timeout_s": 1.0,
        "guided_task.vision.confirm.min_confidence": 0.7,
    })


@pytest.fixture
def mock_services() -> ServiceContainer:
    return ServiceContainer(
        db_factory=MagicMock(),
        bucketizer=MockBucketizer(),
        minio_client=MockMinio(),
        event_aggregator=MockEventAggregator(),
        llm_model_registry=MockLLMRegistry(MockLLMProvider("{}")),
        scene_analysis_client=MockSceneAnalysisClient(),
    )


@pytest.mark.asyncio
async def test_minimal_gate_poll_to_verdict_complete(db_session: Session, db_factory: Any, test_settings: MockSettings, mock_services: ServiceContainer) -> None:
    rule = _make_rule(db_session)
    step1 = _make_step(db_session, rule, 1, "media_window_poll", config={"source": "cts"})
    step2 = _make_step(db_session, rule, 2, "gate_verdict", config={"complete_if": "true", "min_confidence": 0.0})
    _connect(db_session, rule, step1, step2)
    db_session.commit()

    runner = GateGraphRunner(services=mock_services, db_factory=db_factory, settings=test_settings)
    profile = GateProfile(name="confirm", window_s=20, max_frames=9, min_confidence=0.7)
    context = GateRunContext(person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1)

    verdict = await runner.run(gate_rule_id=rule.id, profile=profile, cameras=[], context=context)

    assert verdict.complete is True


@pytest.mark.asyncio
async def test_branchy_gate_cheap_exit(db_session: Session, db_factory: Any, test_settings: MockSettings, mock_services: ServiceContainer) -> None:
    # Set up YOLO detection client to return empty detections (nothing on hob)
    mock_services.scene_analysis_client = MockSceneAnalysisClient(
        SceneAnalyzeResult(detections=[], detector_available=True)
    )
    llm_provider = MockLLMProvider('{"complete": true}')
    mock_services.llm_model_registry = MockLLMRegistry(llm_provider)

    rule = _make_rule(db_session)
    poll = _make_step(db_session, rule, 1, "media_window_poll", config={"source": "cts"})
    yolo = _make_step(db_session, rule, 2, "scene_analysis", config={
        "run_detect": True,
        "image_source": "cts_window",
        "cts_frames_path": "steps.media_window_poll_1.outputs.frames",
    })
    cond = _make_step(db_session, rule, 3, "condition", config={"expression": "steps.scene_analysis_2.outputs.scene_detections | length(@) > 0"})
    heavy = _make_step(db_session, rule, 4, "llm_call", config={
        "prompt": "Is kettle on hob?",
        "heavy": True,
        "output_key": "response",
        "response_format": "json_free",
        "model_id": "vision-model",
    })
    verdict = _make_step(db_session, rule, 5, "gate_verdict", config={"complete_if": "steps.llm_call_4.outputs.response.complete", "min_confidence": 0.0})

    _connect(db_session, rule, poll, yolo)
    _connect(db_session, rule, yolo, cond)
    _connect(db_session, rule, cond, heavy, source_port="true")
    _connect(db_session, rule, heavy, verdict)
    _connect(db_session, rule, cond, verdict, source_port="false")
    db_session.commit()

    runner = GateGraphRunner(services=mock_services, db_factory=db_factory, settings=test_settings)
    profile = GateProfile(name="confirm", window_s=20, max_frames=9, min_confidence=0.7)
    context = GateRunContext(person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1)

    with patch("backend.steps.builtin.scene_analysis._fetch_image", return_value=b"dummy"):
        verdict_res = await runner.run(gate_rule_id=rule.id, profile=profile, cameras=[], context=context)

    # Cond was false, so it should follow the false branch to verdict_false
    assert verdict_res.complete is False
    assert verdict_res.reason == "gate_verdict"
    # assert heavy llm_call never runs
    assert len(llm_provider.calls) == 0


@pytest.mark.asyncio
async def test_branchy_gate_heavy_path(db_session: Session, db_factory: Any, test_settings: MockSettings, mock_services: ServiceContainer) -> None:
    # Set up YOLO detection client to return a detection
    mock_services.scene_analysis_client = MockSceneAnalysisClient(
        SceneAnalyzeResult(detections=[SceneDetection(label="kettle", confidence=0.9, bbox=[0,0,1,1], class_id=1)], detector_available=True)
    )
    llm_provider = MockLLMProvider('{"complete": true, "confidence": 0.95}')
    mock_services.llm_model_registry = MockLLMRegistry(llm_provider)

    rule = _make_rule(db_session)
    poll = _make_step(db_session, rule, 1, "media_window_poll", config={"source": "cts"})
    yolo = _make_step(db_session, rule, 2, "scene_analysis", config={
        "run_detect": True,
        "image_source": "cts_window",
        "cts_frames_path": "steps.media_window_poll_1.outputs.frames",
    })
    cond = _make_step(db_session, rule, 3, "condition", config={"expression": "steps.scene_analysis_2.outputs.scene_detections | length(@) > 0"})
    heavy = _make_step(db_session, rule, 4, "llm_call", config={
        "prompt": "Is kettle on hob?",
        "heavy": True,
        "output_key": "res",
        "response_format": "json_free",
        "model_id": "vision-model",
    })
    verdict = _make_step(db_session, rule, 5, "gate_verdict", config={
        "complete_if": "steps.llm_call_4.outputs.res.complete",
        "confidence_path": "steps.llm_call_4.outputs.res.confidence",
        "reason_path": "steps.llm_call_4.outputs.res.reason",
        "min_confidence": 0.0,
    })

    _connect(db_session, rule, poll, yolo)
    _connect(db_session, rule, yolo, cond)
    _connect(db_session, rule, cond, heavy, source_port="true")
    _connect(db_session, rule, heavy, verdict)
    db_session.commit()

    runner = GateGraphRunner(services=mock_services, db_factory=db_factory, settings=test_settings)
    profile = GateProfile(name="confirm", window_s=20, max_frames=9, min_confidence=0.7)
    context = GateRunContext(person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1)

    with patch("backend.steps.builtin.scene_analysis._fetch_image", return_value=b"dummy"):
        res_verdict = await runner.run(gate_rule_id=rule.id, profile=profile, cameras=[], context=context)

    assert res_verdict.complete is True
    assert res_verdict.confidence == 0.95
    assert len(llm_provider.calls) == 1


@pytest.mark.asyncio
async def test_no_verdict_node_runs_fails_closed(db_session: Session, db_factory: Any, test_settings: MockSettings, mock_services: ServiceContainer) -> None:
    rule = _make_rule(db_session)
    poll = _make_step(db_session, rule, 1, "media_window_poll", config={"source": "cts"})
    cond = _make_step(db_session, rule, 2, "condition", config={"expression": "false"})
    verdict = _make_step(db_session, rule, 3, "gate_verdict", config={"complete_if": "true", "min_confidence": 0.0})
    _connect(db_session, rule, poll, cond)
    _connect(db_session, rule, cond, verdict, source_port="true")
    db_session.commit()

    runner = GateGraphRunner(services=mock_services, db_factory=db_factory, settings=test_settings)
    profile = GateProfile(name="confirm", window_s=20, max_frames=9, min_confidence=0.7)
    context = GateRunContext(person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1)

    res_verdict = await runner.run(gate_rule_id=rule.id, profile=profile, cameras=[], context=context)
    assert res_verdict.complete is False
    assert res_verdict.reason == "no_verdict"


@pytest.mark.asyncio
async def test_non_gate_safe_step_refused(db_session: Session, db_factory: Any, test_settings: MockSettings, mock_services: ServiceContainer) -> None:
    rule = _make_rule(db_session)
    step1 = _make_step(db_session, rule, 1, "notification", config={"channel_type": "telegram"})
    step2 = _make_step(db_session, rule, 2, "gate_verdict", config={"complete_if": "true"})
    _connect(db_session, rule, step1, step2)
    db_session.commit()

    runner = GateGraphRunner(services=mock_services, db_factory=db_factory, settings=test_settings)
    profile = GateProfile(name="confirm", window_s=20, max_frames=9, min_confidence=0.7)
    context = GateRunContext(person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1)

    verdict = await runner.run(gate_rule_id=rule.id, profile=profile, cameras=[], context=context)
    assert verdict.complete is False
    assert verdict.reason == "non_gate_safe_step"


@pytest.mark.asyncio
async def test_node_exception_fails_that_node_closed_not_the_run(db_session: Session, db_factory: Any, test_settings: MockSettings, mock_services: ServiceContainer) -> None:
    rule = _make_rule(db_session)
    poll = _make_step(db_session, rule, 1, "media_window_poll", config={"source": "cts"})
    verdict = _make_step(db_session, rule, 2, "gate_verdict", config={"complete_if": "true", "min_confidence": 0.0})
    _connect(db_session, rule, poll, verdict)
    db_session.commit()

    mock_services.bucketizer.forward_buffer = MagicMock(side_effect=RuntimeError("MinIO connection failed"))

    runner = GateGraphRunner(services=mock_services, db_factory=db_factory, settings=test_settings)
    profile = GateProfile(name="confirm", window_s=20, max_frames=9, min_confidence=0.7)
    context = GateRunContext(person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1)

    verdict_res = await runner.run(gate_rule_id=rule.id, profile=profile, cameras=[], context=context)
    assert verdict_res.complete is False
    assert verdict_res.reason == "no_verdict"


@pytest.mark.asyncio
async def test_node_timeout_fails_closed(db_session: Session, db_factory: Any, test_settings: MockSettings, mock_services: ServiceContainer) -> None:
    rule = _make_rule(db_session)
    poll = _make_step(db_session, rule, 1, "media_window_poll", config={"source": "cts"})
    verdict = _make_step(db_session, rule, 2, "gate_verdict", config={"complete_if": "true", "min_confidence": 0.0})
    _connect(db_session, rule, poll, verdict)
    db_session.commit()

    async def infinite_execute(*args, **kwargs):
        await asyncio.sleep(10.0)
        return StepResult()

    handler = StepRegistry.get("media_window_poll")
    with patch.object(handler, "execute", new=infinite_execute):
        runner = GateGraphRunner(
            services=mock_services,
            db_factory=db_factory,
            settings=test_settings,
            node_timeout_s=0.05,
        )
        profile = GateProfile(name="confirm", window_s=20, max_frames=9, min_confidence=0.7)
        context = GateRunContext(person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1)

        verdict_res = await runner.run(gate_rule_id=rule.id, profile=profile, cameras=[], context=context)
        assert verdict_res.complete is False
        assert verdict_res.reason == "no_verdict"


@pytest.mark.asyncio
async def test_profile_injected_into_pipeline_data(db_session: Session, db_factory: Any, test_settings: MockSettings, mock_services: ServiceContainer) -> None:
    rule = _make_rule(db_session)
    step1 = _make_step(db_session, rule, 1, "media_window_poll", config={"source": "cts", "lookback_s": "inherit", "max_frames": "inherit"})
    step2 = _make_step(db_session, rule, 2, "gate_verdict", config={"complete_if": "true", "min_confidence": 0.0})
    _connect(db_session, rule, step1, step2)
    db_session.commit()

    runner = GateGraphRunner(services=mock_services, db_factory=db_factory, settings=test_settings)
    profile = GateProfile(name="confirm", window_s=25, max_frames=15, min_confidence=0.7)
    context = GateRunContext(person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1)

    with patch("backend.steps.builtin.media_window_poll.collect_recent_cts_frames") as mock_collect:
        mock_collect.return_value = MagicMock(frames=[], images=[], target_cameras=[], partial=False)
        await runner.run(gate_rule_id=rule.id, profile=profile, cameras=[], context=context)

        _, kwargs = mock_collect.call_args
        config_passed = kwargs["config"]
        assert config_passed.lookback_s == 25.0
        assert config_passed.max_frames == 15


@pytest.mark.asyncio
async def test_cameras_injected(db_session: Session, db_factory: Any, test_settings: MockSettings, mock_services: ServiceContainer) -> None:
    rule = _make_rule(db_session)
    step1 = _make_step(db_session, rule, 1, "media_window_poll", config={"source": "auto"})
    step2 = _make_step(db_session, rule, 2, "gate_verdict", config={"complete_if": "true", "min_confidence": 0.0})
    _connect(db_session, rule, step1, step2)
    db_session.commit()

    runner = GateGraphRunner(services=mock_services, db_factory=db_factory, settings=test_settings)
    profile = GateProfile(name="confirm", window_s=20, max_frames=9, min_confidence=0.7)
    cameras = [ResolvedCamera(id="camera_a", source="cts"), ResolvedCamera(id="camera_b", source="recamera")]
    context = GateRunContext(person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1)

    with patch("backend.steps.builtin.media_window_poll.collect_recent_frames_multi_source") as mock_collect:
        mock_collect.return_value = {"frames": [], "images": [], "partial": False}
        await runner.run(gate_rule_id=rule.id, profile=profile, cameras=cameras, context=context)

        _, kwargs = mock_collect.call_args
        cameras_passed = kwargs["cameras"]
        assert len(cameras_passed) == 2
        assert cameras_passed[0].id == "camera_a"
        assert cameras_passed[1].id == "camera_b"


@pytest.mark.asyncio
async def test_prune_heavy_skips_tagged_node_in_watch(db_session: Session, db_factory: Any, test_settings: MockSettings, mock_services: ServiceContainer) -> None:
    llm_provider = MockLLMProvider('{"complete": true}')
    mock_services.llm_model_registry = MockLLMRegistry(llm_provider)

    rule = _make_rule(db_session)
    poll = _make_step(db_session, rule, 1, "media_window_poll", config={"source": "cts"})
    heavy = _make_step(db_session, rule, 2, "llm_call", config={
        "prompt": "VLM confirm",
        "heavy": True,
        "output_key": "response",
        "response_format": "json_free",
        "model_id": "vision-model",
    })
    verdict = _make_step(db_session, rule, 3, "gate_verdict", config={"complete_if": "steps.llm_call_2.outputs.response.complete", "min_confidence": 0.0})

    _connect(db_session, rule, poll, heavy)
    _connect(db_session, rule, heavy, verdict)
    db_session.commit()

    runner = GateGraphRunner(services=mock_services, db_factory=db_factory, settings=test_settings)
    context = GateRunContext(person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1)

    # 1. Watch profile (prune_heavy=True)
    watch_profile = GateProfile(name="watch", window_s=4, max_frames=3, min_confidence=0.7, prune_heavy=True)
    verdict_watch = await runner.run(gate_rule_id=rule.id, profile=watch_profile, cameras=[], context=context)

    assert verdict_watch.complete is False
    assert verdict_watch.reason == "no_verdict"  # heavy pruned, so verdict step not reached
    assert len(llm_provider.calls) == 0

    # 2. Confirm profile (prune_heavy=False)
    confirm_profile = GateProfile(name="confirm", window_s=20, max_frames=9, min_confidence=0.7, prune_heavy=False)
    verdict_confirm = await runner.run(gate_rule_id=rule.id, profile=confirm_profile, cameras=[], context=context)

    assert verdict_confirm.complete is True
    assert len(llm_provider.calls) == 1


@pytest.mark.asyncio
async def test_profile_model_override(db_session: Session, db_factory: Any, test_settings: MockSettings, mock_services: ServiceContainer) -> None:
    llm_provider = MockLLMProvider('{"complete": true}')
    mock_services.llm_model_registry = MockLLMRegistry(llm_provider)

    rule = _make_rule(db_session)
    poll = _make_step(db_session, rule, 1, "media_window_poll", config={"source": "cts"})
    llm = _make_step(db_session, rule, 2, "llm_call", config={"prompt": "VLM confirm", "model_id": "step-model", "use_profile_model": True})
    verdict = _make_step(db_session, rule, 3, "gate_verdict", config={"complete_if": "true", "min_confidence": 0.0})

    _connect(db_session, rule, poll, llm)
    _connect(db_session, rule, llm, verdict)
    db_session.commit()

    runner = GateGraphRunner(services=mock_services, db_factory=db_factory, settings=test_settings)
    context = GateRunContext(person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1)

    profile = GateProfile(name="confirm", window_s=20, max_frames=9, min_confidence=0.7, model_id="profile-override-model")
    await runner.run(gate_rule_id=rule.id, profile=profile, cameras=[], context=context)

    assert len(llm_provider.calls) == 1
    assert llm_provider.calls[0]["prompt"].strip() != ""


@pytest.mark.asyncio
async def test_no_llm_registry_fails_closed(db_session: Session, db_factory: Any, test_settings: MockSettings, mock_services: ServiceContainer) -> None:
    # Set model registry to None
    mock_services.llm_model_registry = None

    rule = _make_rule(db_session)
    poll = _make_step(db_session, rule, 1, "media_window_poll", config={"source": "cts"})
    llm = _make_step(db_session, rule, 2, "llm_call", config={"prompt": "VLM confirm", "model_id": "vision-model"})
    verdict = _make_step(db_session, rule, 3, "gate_verdict", config={
        "complete_if": "steps.llm_call_2.outputs.llm_response.complete",
    })

    _connect(db_session, rule, poll, llm)
    _connect(db_session, rule, llm, verdict)
    db_session.commit()

    runner = GateGraphRunner(services=mock_services, db_factory=db_factory, settings=test_settings)
    profile = GateProfile(name="confirm", window_s=20, max_frames=9, min_confidence=0.7)
    context = GateRunContext(person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1)

    verdict_res = await runner.run(gate_rule_id=rule.id, profile=profile, cameras=[], context=context)
    assert verdict_res.complete is False


@pytest.mark.asyncio
async def test_output_namespace_matches_executor(db_session: Session, db_factory: Any, test_settings: MockSettings, mock_services: ServiceContainer) -> None:
    rule = _make_rule(db_session)
    poll = _make_step(db_session, rule, 1, "media_window_poll", config={"source": "cts"}, label="my_poll")
    verdict = _make_step(db_session, rule, 2, "gate_verdict", config={
        "complete_if": "steps.my_poll.outputs.source == 'cts'",
        "min_confidence": 0.0,
    })
    _connect(db_session, rule, poll, verdict)
    db_session.commit()

    runner = GateGraphRunner(services=mock_services, db_factory=db_factory, settings=test_settings)
    profile = GateProfile(name="confirm", window_s=20, max_frames=9, min_confidence=0.7)
    context = GateRunContext(person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1)

    verdict_res = await runner.run(gate_rule_id=rule.id, profile=profile, cameras=[], context=context)
    assert verdict_res.complete is True


@pytest.mark.asyncio
async def test_runner_never_persists(db_session: Session, db_factory: Any, test_settings: MockSettings, mock_services: ServiceContainer) -> None:
    rule = _make_rule(db_session)
    poll = _make_step(db_session, rule, 1, "media_window_poll", config={"source": "cts"})
    verdict = _make_step(db_session, rule, 2, "gate_verdict", config={"complete_if": "true", "min_confidence": 0.0})
    _connect(db_session, rule, poll, verdict)
    db_session.commit()

    runner = GateGraphRunner(services=mock_services, db_factory=db_factory, settings=test_settings)
    profile = GateProfile(name="confirm", window_s=20, max_frames=9, min_confidence=0.7)
    context = GateRunContext(person_id="p1", room_name="Living Room", sensor_id="s1", session_id="sess1", step_ord=1)

    execs_before = db_session.query(WorkflowExecution).count()

    await runner.run(gate_rule_id=rule.id, profile=profile, cameras=[], context=context)

    execs_after = db_session.query(WorkflowExecution).count()
    assert execs_before == execs_after  # Assert no WorkflowExecution was created


def test_cool_off_cache_operations() -> None:
    cache = _CoolOffCache()
    key = ("sess1", 1, "confirm")

    verdict = GateVerdict(
        complete=True,
        confidence=0.9,
        reason="test",
        node_results={},
        cost={},
        profile="confirm",
    )

    now = datetime(2026, 6, 19, 12, 0, 0, tzinfo=UTC)

    # Cache is cold
    assert cache.get_fresh(key, min_interval_s=15, now=now) is None

    # Store verdict
    cache.put(key, verdict, now=now)

    # Fresh retrieve within interval
    assert cache.get_fresh(key, min_interval_s=15, now=now + timedelta(seconds=10)) == verdict

    # Expired retrieve
    assert cache.get_fresh(key, min_interval_s=15, now=now + timedelta(seconds=20)) is None

    # Key includes profile, confirm shouldn't fetch watch
    watch_key = ("sess1", 1, "watch")
    assert cache.get_fresh(watch_key, min_interval_s=15, now=now + timedelta(seconds=10)) is None
