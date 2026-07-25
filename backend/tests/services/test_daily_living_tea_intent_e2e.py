"""DL-M06 Part E.4: end-to-end test driving the tea-intent shadow-detector
rule bundle through the real RulesEngine (context filters) and
PipelineExecutor (step graph). Only the perception/vision steps
(media_window_poll, scene_analysis, llm_call) are stubbed with fakes;
region_presence, both condition steps, signal_emit, and notification run for
real, so this proves the cheap-first cascade actually wires together, not
just that each step passes its own unit test in isolation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.filters import FilterRegistry
from backend.models.cts_signal import DementiaSignal
from backend.models.rule import Rule
from backend.schemas.rule_bundle import RuleBundle
from backend.services.pipeline_executor import PipelineExecutor
from backend.services.rule_importer import bundle_to_rule
from backend.services.rules_engine import RulesEngine
from backend.services.signals import SignalsService
from backend.steps import StepRegistry
from backend.steps.base import ServiceContainer, StepResult, TriggerContext

StepRegistry.discover()
FilterRegistry.discover()

_BUNDLE_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "rule_bundles"
    / "daily_living_tea_intent_shadow.json"
)

_PERSON_ID = "test_resident"
_KITCHEN_ROOM = "kitchen"
_KITCHEN_CAM = "test_kitchen_cam"

# Fixed clock inside the bundle's time_range context (06:00-21:00 UTC). The
# suite must not depend on wall-clock time: RulesEngine.get_matching_rules_for_cron
# evaluates the rule's time_range/presence_dwell contexts against "now", and a
# real midnight-to-6am or 9pm-to-midnight UTC test run would otherwise make
# every assertion in this file vacuously true (should_fire is False, _tick
# returns None without ever exercising the pipeline).
_NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)

_PLACEHOLDERS = {
    "__RESIDENT_PERSON_ID__": _PERSON_ID,
    "__KITCHEN_ROOM_NAME__": _KITCHEN_ROOM,
    "__KITCHEN_CAMERA_SENSOR_ID__": _KITCHEN_CAM,
}


def _load_rule(db_session) -> Rule:
    raw = _BUNDLE_PATH.read_text()
    for placeholder, value in _PLACEHOLDERS.items():
        raw = raw.replace(placeholder, value)
    bundle = RuleBundle(**json.loads(raw))
    report = bundle_to_rule(bundle, db_session, app_version="test")
    assert report.status == "ok", report.errors
    db_session.commit()
    return db_session.get(Rule, report.rule_id)


class _FakeStatus:
    def __init__(self, value: str) -> None:
        self.value = value


class _FakeSnapshot:
    def __init__(self, status: str, room_name: str | None, dwell_minutes: float | None) -> None:
        self.status = _FakeStatus(status)
        self.room_id = room_name
        self.room_name = room_name
        self.dwell_minutes = dwell_minutes
        self.confidence = 0.9
        self.last_seen_at = None
        self.sources: tuple = ()
        self.notes = None


class _FakePresenceService:
    def __init__(self) -> None:
        self.snapshot = _FakeSnapshot(
            status="present_room", room_name=_KITCHEN_ROOM, dwell_minutes=5.0
        )

    async def get(self, person_id: str, *, at=None):
        return self.snapshot


class _FakeNotificationDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def dispatch(self, **kwargs):
        self.calls.append(kwargs)
        return {"telegram": True}


_KETTLE_COUNTER_DETECTION = {
    "label": "person",
    "confidence": 0.9,
    "bbox": [0.6, 0.2, 0.8, 0.7],
    "bbox_normalized": True,
}

_AWAY_FROM_COUNTER_DETECTION = {
    "label": "person",
    "confidence": 0.9,
    "bbox": [0.05, 0.2, 0.2, 0.7],
    "bbox_normalized": True,
}


def _make_services(db_factory, notification_dispatcher) -> ServiceContainer:
    return ServiceContainer(
        db_factory=db_factory,
        presence=_FakePresenceService(),
        signals=SignalsService(db_factory=db_factory),
        notification_dispatcher=notification_dispatcher,
    )


def _stub_executor(executor, *, in_region_detection, llm_verdict):
    """Stub media_window_poll/scene_analysis/llm_call; let the rest run for real."""
    original = executor._execute_step

    async def _patched(step, execution, pipeline_data, trigger):
        if step.step_type == "media_window_poll":
            return StepResult(data={"images": ["http://minio.nanai.internal/frame.jpg"]})
        if step.step_type == "scene_analysis":
            return StepResult(
                data={
                    "scene_description": "a person standing near the counter",
                    "scene_detections": [in_region_detection],
                }
            )
        if step.step_type == "llm_call":
            return StepResult(data={"tea_verdict": llm_verdict})
        return await original(step, execution, pipeline_data, trigger)

    executor._execute_step = _patched


def _signal_rows(db_session) -> list[DementiaSignal]:
    db_session.expire_all()
    return (
        db_session.query(DementiaSignal)
        .filter(
            DementiaSignal.person_id == _PERSON_ID,
            DementiaSignal.signal_type == "tea_intent_suspected",
        )
        .all()
    )


async def _tick(rule, db_session, engine, executor):
    should_fire = await engine.get_matching_rules_for_cron(rule, db_session, now=_NOW)
    assert should_fire, "rule must fire for this test's assertions to be meaningful"
    return await executor.execute(rule, TriggerContext(trigger_type="cron"), db_session)


class TestPositiveVerdict:
    async def test_positive_verdict_emits_one_signal_and_one_notification(
        self, db_session, db_factory
    ):
        rule = _load_rule(db_session)
        dispatcher = _FakeNotificationDispatcher()
        services = _make_services(db_factory, dispatcher)
        engine = RulesEngine(services, tz_name="UTC")
        executor = PipelineExecutor(services)
        _stub_executor(
            executor,
            in_region_detection=_KETTLE_COUNTER_DETECTION,
            llm_verdict={"tea_intent": True, "confidence": 0.82, "reason": "hand near kettle"},
        )

        await _tick(rule, db_session, engine, executor)

        rows = _signal_rows(db_session)
        assert len(rows) == 1
        assert rows[0].severity == "info"
        assert rows[0].value == pytest.approx(0.82)
        assert rows[0].evidence_grade == "experimental"
        assert rows[0].context_json["reason"] == "hand near kettle"

        assert len(dispatcher.calls) == 1
        assert "tea" in dispatcher.calls[0]["message"].lower()


class TestNegativeVerdict:
    async def test_negative_verdict_emits_neither_signal_nor_notification(
        self, db_session, db_factory
    ):
        rule = _load_rule(db_session)
        dispatcher = _FakeNotificationDispatcher()
        services = _make_services(db_factory, dispatcher)
        engine = RulesEngine(services, tz_name="UTC")
        executor = PipelineExecutor(services)
        _stub_executor(
            executor,
            in_region_detection=_KETTLE_COUNTER_DETECTION,
            llm_verdict={"tea_intent": False, "confidence": 0.15, "reason": "just passing by"},
        )

        await _tick(rule, db_session, engine, executor)

        assert _signal_rows(db_session) == []
        assert dispatcher.calls == []

    async def test_person_outside_kettle_region_never_reaches_the_llm(
        self, db_session, db_factory
    ):
        """The tier-1 region gate must skip the tier-3 llm_call entirely when
        she is not at the kettle counter, not merely produce a negative
        verdict; this test would fail if in_region_check's false branch let
        the llm_call step run anyway."""
        rule = _load_rule(db_session)
        dispatcher = _FakeNotificationDispatcher()
        services = _make_services(db_factory, dispatcher)
        engine = RulesEngine(services, tz_name="UTC")
        executor = PipelineExecutor(services)

        llm_called = False
        original = executor._execute_step

        async def _patched(step, execution, pipeline_data, trigger):
            nonlocal llm_called
            if step.step_type == "media_window_poll":
                return StepResult(data={"images": ["http://minio.nanai.internal/frame.jpg"]})
            if step.step_type == "scene_analysis":
                return StepResult(
                    data={
                        "scene_description": "a person standing across the kitchen",
                        "scene_detections": [_AWAY_FROM_COUNTER_DETECTION],
                    }
                )
            if step.step_type == "llm_call":
                llm_called = True
                return StepResult(data={"tea_verdict": {"tea_intent": True, "confidence": 0.9}})
            return await original(step, execution, pipeline_data, trigger)

        executor._execute_step = _patched

        await _tick(rule, db_session, engine, executor)

        assert llm_called is False
        assert _signal_rows(db_session) == []
        assert dispatcher.calls == []
