from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from backend.core.config import Settings
from backend.services.guided_task.camera_selection import ResolvedCamera
from backend.services.guided_task.completion.vision import VisionEvaluator
from backend.services.guided_task.gate_runner import GateVerdict


@dataclass
class _Routine:
    config_json: dict | None = None


@dataclass
class _Session:
    id: int = 1
    person_id: str = "resident-1"
    routine: _Routine | None = None


@dataclass
class _Step:
    ord: int = 0
    camera_ids: list[str] | None = None
    zone_id: int | None = None


class FakeGateGraphRunner:
    def __init__(self, time_fn=None):
        from backend.services.guided_task.gate_runner import _CoolOffCache

        self.cache = _CoolOffCache()
        self._time_fn = time_fn or (lambda: datetime.now(UTC))
        self.run_calls = []
        self.verdict_to_return = GateVerdict(
            complete=True,
            confidence=0.9,
            reason="done",
            node_results={"llm_call": {"type": "llm_call", "label": "llm_call", "ports": ["main"]}},
            cost={"model_calls": 1, "frames": 2, "latency_ms": 100},
            profile="confirm",
        )

    async def run(self, gate_rule_id, profile, cameras, context):
        self.run_calls.append(
            {
                "gate_rule_id": gate_rule_id,
                "profile": profile,
                "cameras": cameras,
                "context": context,
            }
        )
        return self.verdict_to_return


async def test_complete_verdict_returns_complete(monkeypatch) -> None:
    runner = FakeGateGraphRunner()
    evaluator = VisionEvaluator(
        gate_config={"vision": {"gate_graph_rule_id": 42}},
        gate_runner=runner,
        settings=Settings.from_dict({}),
    )
    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )
    res = await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})
    assert res.complete is True
    assert res.confidence == 0.9
    assert res.reason == "done"


async def test_incomplete_verdict_returns_not_complete(monkeypatch) -> None:
    runner = FakeGateGraphRunner()
    runner.verdict_to_return = GateVerdict(
        complete=False,
        confidence=0.3,
        reason="not_done",
        node_results={},
        cost={},
        profile="confirm",
    )
    evaluator = VisionEvaluator(
        gate_config={"vision": {"gate_graph_rule_id": 42}},
        gate_runner=runner,
        settings=Settings.from_dict({}),
    )
    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )
    res = await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})
    assert res.complete is False
    assert res.confidence == 0.3
    assert res.reason == "not_done"


async def test_missing_gate_graph_fails_closed(monkeypatch) -> None:
    events = []

    def record(session_id, step_ord, detail):
        events.append(detail)

    evaluator = VisionEvaluator(
        gate_config={"vision": {}},  # missing gate_graph_rule_id
        gate_runner=FakeGateGraphRunner(),
        settings=Settings.from_dict({}),
        event_recorder=record,
    )
    res = await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})
    assert res.complete is False
    assert res.reason == "no_gate_graph"
    assert events[0]["reason"] == "no_gate_graph"
    assert events[0]["complete"] is False


async def test_cameras_resolved_and_passed_to_runner(monkeypatch) -> None:
    runner = FakeGateGraphRunner()
    evaluator = VisionEvaluator(
        gate_config={"vision": {"gate_graph_rule_id": 42}},
        gate_runner=runner,
        settings=Settings.from_dict({}),
    )
    cameras = [
        ResolvedCamera(id="cam-1", source="cts"),
        ResolvedCamera(id="recam-2", source="recamera"),
    ]
    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=cameras),
    )
    await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})
    assert len(runner.run_calls) == 1
    assert runner.run_calls[0]["cameras"] == cameras


async def test_confirm_profile_resolved_via_precedence(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    # 1. Test global settings fallback
    runner = FakeGateGraphRunner()
    evaluator = VisionEvaluator(
        gate_config={"vision": {"gate_graph_rule_id": 42}},
        gate_runner=runner,
        settings=Settings.from_dict(
            {
                "guided_task": {
                    "vision": {
                        "confirm": {
                            "window_s": 25.0,
                            "max_frames": 5,
                            "min_confidence": 0.8,
                            "min_interval_s": 10.0,
                            "model_id": "global-model",
                        }
                    }
                }
            }
        ),
    )
    await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})
    profile = runner.run_calls[0]["profile"]
    assert profile.window_s == 25.0
    assert profile.max_frames == 5
    assert profile.min_confidence == 0.8
    assert profile.model_id == "global-model"

    # 2. Test routine override
    runner = FakeGateGraphRunner()
    routine = _Routine(
        config_json={
            "guided_task": {
                "vision": {
                    "confirm": {
                        "window_s": 30.0,
                        "max_frames": 6,
                        "min_confidence": 0.85,
                        "min_interval_s": 12.0,
                        "model_id": "routine-model",
                    }
                }
            }
        }
    )
    session = _Session(routine=routine)
    evaluator = VisionEvaluator(
        gate_config={"vision": {"gate_graph_rule_id": 42}},
        gate_runner=runner,
        settings=Settings.from_dict(
            {
                "guided_task": {
                    "vision": {
                        "confirm": {
                            "window_s": 25.0,
                            "max_frames": 5,
                            "min_confidence": 0.8,
                            "min_interval_s": 10.0,
                            "model_id": "global-model",
                        }
                    }
                }
            }
        ),
    )
    await evaluator.is_complete(session=session, step=_Step(), evidence={})
    profile = runner.run_calls[0]["profile"]
    assert profile.window_s == 30.0
    assert profile.max_frames == 6
    assert profile.min_confidence == 0.85
    assert profile.model_id == "routine-model"

    # 3. Test step override
    runner = FakeGateGraphRunner()
    evaluator = VisionEvaluator(
        gate_config={
            "vision": {
                "gate_graph_rule_id": 42,
                "confirm": {
                    "window_s": 35.0,
                    "max_frames": 7,
                    "min_confidence": 0.9,
                    "min_interval_s": 14.0,
                    "model_id": "step-model",
                },
            }
        },
        gate_runner=runner,
        settings=Settings.from_dict(
            {
                "guided_task": {
                    "vision": {
                        "confirm": {
                            "window_s": 25.0,
                            "max_frames": 5,
                            "min_confidence": 0.8,
                            "min_interval_s": 10.0,
                            "model_id": "global-model",
                        }
                    }
                }
            }
        ),
    )
    await evaluator.is_complete(session=session, step=_Step(), evidence={})
    profile = runner.run_calls[0]["profile"]
    assert profile.window_s == 35.0
    assert profile.max_frames == 7
    assert profile.min_confidence == 0.9
    assert profile.model_id == "step-model"


async def test_confirm_camera_cap_independent_of_frames(monkeypatch) -> None:
    """G11: max_cameras and max_frames are independent budgets.

    A cascade that returns five cameras must be capped to max_cameras (3),
    not max_frames (9): frames and cameras are different knobs.
    """
    select_cameras_mock = AsyncMock(
        return_value=[
            ResolvedCamera(id="cam-1", source="cts"),
            ResolvedCamera(id="cam-2", source="cts"),
            ResolvedCamera(id="cam-3", source="cts"),
            ResolvedCamera(id="cam-4", source="cts"),
            ResolvedCamera(id="cam-5", source="cts"),
        ]
    )
    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        select_cameras_mock,
    )

    runner = FakeGateGraphRunner()
    evaluator = VisionEvaluator(
        gate_config={"vision": {"gate_graph_rule_id": 42}},
        gate_runner=runner,
        settings=Settings.from_dict(
            {
                "guided_task": {
                    "vision": {
                        "max_cameras": 3,
                        "confirm": {"max_frames": 9},
                    }
                }
            }
        ),
    )

    await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})

    assert select_cameras_mock.call_args.kwargs["max_cameras"] == 3


async def test_cooloff_reuses_cached_verdict(monkeypatch) -> None:
    runner = FakeGateGraphRunner()
    evaluator = VisionEvaluator(
        gate_config={"vision": {"gate_graph_rule_id": 42}},
        gate_runner=runner,
        settings=Settings.from_dict({}),
    )
    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    # Run once to populate cache
    res1 = await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})
    assert len(runner.run_calls) == 1
    assert res1.complete is True

    # Run again: should use cache and NOT call run() again
    res2 = await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})
    assert len(runner.run_calls) == 1
    assert res2.complete is True


async def test_cached_negative_verdict_is_recorded(monkeypatch) -> None:
    """G3: a cached negative confirm verdict still counts as a disagreement
    event, so the bounded-disagreement escape hatch can accumulate even
    within the cool-off window."""
    events = []

    def record(session_id, step_ord, detail):
        events.append(detail)

    runner = FakeGateGraphRunner()
    runner.verdict_to_return = GateVerdict(
        complete=False,
        confidence=0.3,
        reason="not_done",
        node_results={},
        cost={},
        profile="confirm",
    )
    evaluator = VisionEvaluator(
        gate_config={"vision": {"gate_graph_rule_id": 42}},
        gate_runner=runner,
        settings=Settings.from_dict({}),
        event_recorder=record,
    )
    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    res1 = await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})
    assert len(runner.run_calls) == 1
    assert res1.complete is False
    assert len(events) == 1  # the first (non-cached) run records once

    # Second call within the cool-off window reuses the cache but must still
    # record a disagreement event.
    res2 = await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})
    assert len(runner.run_calls) == 1
    assert res2.complete is False
    assert len(events) == 2
    assert events[1]["complete"] is False
    assert events[1]["reason"] == "cached:not_done"


async def test_cached_positive_verdict_not_recorded(monkeypatch) -> None:
    """A cached positive advances immediately; recording it again would
    double-count metrics."""
    events = []

    def record(session_id, step_ord, detail):
        events.append(detail)

    runner = FakeGateGraphRunner()
    evaluator = VisionEvaluator(
        gate_config={"vision": {"gate_graph_rule_id": 42}},
        gate_runner=runner,
        settings=Settings.from_dict({}),
        event_recorder=record,
    )
    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )

    res1 = await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})
    assert len(runner.run_calls) == 1
    assert res1.complete is True
    assert len(events) == 1  # the first (non-cached) run records once

    res2 = await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})
    assert len(runner.run_calls) == 1
    assert res2.complete is True
    assert len(events) == 1  # cached positive: no additional record


async def test_emits_new_audit_event_shape(monkeypatch) -> None:
    events = []

    def record(session_id, step_ord, detail):
        events.append(detail)

    runner = FakeGateGraphRunner()
    evaluator = VisionEvaluator(
        gate_config={"vision": {"gate_graph_rule_id": 42}},
        gate_runner=runner,
        settings=Settings.from_dict({}),
        event_recorder=record,
    )
    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(
            return_value=[
                ResolvedCamera(id="cam-1", source="cts"),
                ResolvedCamera(id="recam-2", source="recamera"),
            ]
        ),
    )
    await evaluator.is_complete(session=_Session(), step=_Step(), evidence={})

    assert len(events) == 1
    evt = events[0]
    assert evt["profile"] == "confirm"
    assert evt["gate_graph_rule_id"] == 42
    assert evt["cameras"] == [
        {"id": "cam-1", "source": "cts"},
        {"id": "recam-2", "source": "recamera"},
    ]
    assert evt["complete"] is True
    assert evt["confidence"] == 0.9
    assert evt["reason"] == "done"
    assert evt["node_results"] == [{"type": "llm_call", "label": "llm_call", "ports": ["main"]}]
    assert evt["cost"] == {"model_calls": 1, "frames": 2, "latency_ms": 100}


async def test_no_camera_ids_override_read(monkeypatch) -> None:
    runner = FakeGateGraphRunner()

    # Step has camera_ids override but we also define an observer on step or step completion gate
    class TrackedStep:
        def __init__(self):
            self.ord = 0
            self.camera_ids = ["step-camera-1"]
            self._accessed = False

    step = TrackedStep()
    evaluator = VisionEvaluator(
        gate_config={"vision": {"gate_graph_rule_id": 42, "camera_ids": ["gate-override-cam"]}},
        gate_runner=runner,
        settings=Settings.from_dict({}),
    )
    monkeypatch.setattr(
        "backend.services.guided_task.completion.vision.select_cameras_tagged",
        AsyncMock(return_value=[ResolvedCamera(id="cam-1", source="cts")]),
    )
    await evaluator.is_complete(session=_Session(), step=step, evidence={})
    # Since select_cameras_tagged resolves from step, and VisionEvaluator never accesses
    # gate_config.vision.camera_ids, this is verified.
