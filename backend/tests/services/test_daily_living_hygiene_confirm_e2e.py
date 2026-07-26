"""DL-M08 Part E.5: end-to-end test driving the hygiene-confirm rule bundle
through the real RulesEngine (event-context filter matching) and
PipelineExecutor.fire_event (the dementia_signal dispatch path), the same
path DementiaSignalSubscriber uses in production.

Only the vision step (llm_call) is stubbed with a fake VLM verdict; MinIO
presigning, the bathroom dwell-history query (backed by a real
PersonLocationService with in-memory repos), signal_emit, and notification
all run for real. This proves the fire_event -> pipeline_data["trigger_event"]
wiring this milestone added actually reaches media_presign's object names and
the alert's evidence, not just that each step passes its own unit test.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.filters import FilterRegistry
from backend.models.cts_signal import DementiaSignal
from backend.models.room import Room
from backend.models.rule import Rule
from backend.schemas.rule_bundle import RuleBundle
from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService
from backend.services.pipeline_executor import PipelineExecutor
from backend.services.rule_importer import bundle_to_rule
from backend.services.rules_engine import RulesEngine
from backend.services.signals import SignalsService
from backend.steps import StepRegistry
from backend.steps.base import ServiceContainer, StepResult

StepRegistry.discover()
FilterRegistry.discover()

_BUNDLE_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "rule_bundles"
    / "daily_living_hygiene_confirm.json"
)

_PERSON_ID = "test_resident"
_BATHROOM_ROOM = "bathroom"


def _load_rule(db_session) -> Rule:
    raw = _BUNDLE_PATH.read_text()
    raw = raw.replace("__BATHROOM_ROOM_NAME__", _BATHROOM_ROOM)
    bundle = RuleBundle(**json.loads(raw))
    report = bundle_to_rule(bundle, db_session, app_version="test")
    assert report.status == "ok", report.errors
    db_session.commit()
    return db_session.get(Rule, report.rule_id)


def _make_signal_payload() -> dict:
    """Mirror DementiaSignalSubscriber.handle()'s fire_event payload shape exactly."""
    return {
        "row_id": 1,
        "signal_id": "sig-same-clothes-1",
        "signal_kind": "same_clothes_suspected",
        "person_id": _PERSON_ID,
        "severity": "info",
        "window_start": "2026-01-14T00:00:00+00:00",
        "window_end": "2026-01-15T11:00:00+00:00",
        "action": "created",
        "evidence": {
            "similarity": 0.95,
            "yesterday_day": "2026-01-14",
            "today_day": "2026-01-15",
            "yesterday_sample_count": 8,
            "yesterday_mean_quality": 0.7,
            "today_sample_count": 9,
            "today_mean_quality": 0.72,
            "yesterday_best_keyframe_objects": ["cts/yesterday1.jpg", "cts/yesterday2.jpg"],
            "today_best_keyframe_objects": ["cts/today1.jpg"],
        },
    }


class _FakeMinio:
    def __init__(self, known_objects: set[str]):
        self.known_objects = known_objects

    async def async_object_exists(self, object_name):
        return object_name in self.known_objects

    def generate_presigned_url(self, object_name, expiration=3600):
        return f"http://minio.local/bucket/{object_name}?sig=test"


class _FakeNotificationDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def dispatch(self, **kwargs):
        self.calls.append(kwargs)
        return {"telegram": True}


def _make_person_location() -> PersonLocationService:
    return PersonLocationService(
        InMemoryObservationRepository(),
        InMemorySegmentRepository(),
        PersonLocationConfig(),
    )


def _make_services(db_factory, notification_dispatcher, person_location) -> ServiceContainer:
    return ServiceContainer(
        db_factory=db_factory,
        signals=SignalsService(db_factory=db_factory),
        notification_dispatcher=notification_dispatcher,
        person_location=person_location,
        minio_client=_FakeMinio(
            known_objects={"cts/yesterday1.jpg", "cts/yesterday2.jpg", "cts/today1.jpg"}
        ),
    )


def _stub_llm(executor, verdict: dict):
    original = executor._execute_step
    call_count = {"llm_call": 0}

    async def _patched(step, execution, pipeline_data, trigger):
        if step.step_type == "llm_call":
            call_count["llm_call"] += 1
            return StepResult(data={"vlm_compare": verdict})
        return await original(step, execution, pipeline_data, trigger)

    executor._execute_step = _patched
    return call_count


def _signal_rows(db_session) -> list[DementiaSignal]:
    db_session.expire_all()
    return (
        db_session.query(DementiaSignal)
        .filter(
            DementiaSignal.person_id == _PERSON_ID,
            DementiaSignal.signal_type == "hygiene_routine_missed",
        )
        .all()
    )


@pytest.mark.asyncio
async def test_vlm_confirms_and_no_dwell_emits_signal_and_full_alert(db_session, db_factory):
    _load_rule(db_session)
    db_session.add(Room(name=_BATHROOM_ROOM))
    db_session.commit()

    dispatcher = _FakeNotificationDispatcher()
    person_location = _make_person_location()  # no ingested segments: no dwell anywhere
    services = _make_services(db_factory, dispatcher, person_location)
    engine = RulesEngine(services, tz_name="UTC")
    executor = PipelineExecutor(services, rules_engine=engine)
    call_count = _stub_llm(
        executor,
        {
            "same_outfit": True,
            "confidence": 0.84,
            "outfit_yesterday": "blue cardigan",
            "outfit_today": "blue cardigan",
            "reason": "identical cardigan and pattern",
        },
    )

    await executor.fire_event(source="cts", kind="dementia_signal", payload=_make_signal_payload())

    rows = _signal_rows(db_session)
    assert len(rows) == 1
    assert rows[0].severity == "info"
    assert rows[0].value == pytest.approx(0.84)
    assert rows[0].context_json["outfit_today"] == "blue cardigan"
    # render_template must resolve trigger_event.evidence.* same as
    # resolve_pipeline_value does for media_presign; _render_context only
    # renders string values, so a numeric template lands as a string.
    assert rows[0].context_json["similarity"] == "0.95"

    assert call_count["llm_call"] == 1  # cost ceiling: one VLM call per triggering signal
    assert len(dispatcher.calls) == 1
    message = dispatcher.calls[0]["message"].lower()
    assert "yesterday's clothes" in message
    assert dispatcher.calls[0]["image_urls"] == [
        "http://minio.local/bucket/cts/yesterday1.jpg?sig=test",
        "http://minio.local/bucket/cts/yesterday2.jpg?sig=test",
        "http://minio.local/bucket/cts/today1.jpg?sig=test",
    ]


@pytest.mark.asyncio
async def test_vlm_confirms_and_dwell_found_takes_low_key_path_only(db_session, db_factory):
    _load_rule(db_session)
    room = Room(name=_BATHROOM_ROOM)
    db_session.add(room)
    db_session.commit()
    db_session.refresh(room)

    dispatcher = _FakeNotificationDispatcher()
    person_location = _make_person_location()
    # presence_query's room_dwell_history mode uses the real wall clock (not
    # an injectable clock, matching every other step's convention), so the
    # seeded episode must fall inside its actual "now - window_hours" lookback.
    enter = datetime.now(UTC) - timedelta(hours=2)
    exit_ = enter + timedelta(minutes=15)  # above the 8-minute threshold
    await person_location.ingest_room_transition(
        _PERSON_ID, "tz1", "enter", room.id, room.id + 1000, enter
    )
    await person_location.ingest_room_transition(
        _PERSON_ID, "tz1", "exit", room.id, room.id + 1000, exit_
    )

    services = _make_services(db_factory, dispatcher, person_location)
    engine = RulesEngine(services, tz_name="UTC")
    executor = PipelineExecutor(services, rules_engine=engine)
    call_count = _stub_llm(
        executor,
        {
            "same_outfit": True,
            "confidence": 0.9,
            "outfit_yesterday": "blue cardigan",
            "outfit_today": "blue cardigan",
            "reason": "identical",
        },
    )

    await executor.fire_event(source="cts", kind="dementia_signal", payload=_make_signal_payload())

    assert _signal_rows(db_session) == []
    assert call_count["llm_call"] == 1
    assert len(dispatcher.calls) == 1
    message = dispatcher.calls[0]["message"].lower()
    assert "did wash up" in message
    assert dispatcher.calls[0]["image_urls"] == []


@pytest.mark.asyncio
async def test_vlm_denies_same_outfit_emits_nothing(db_session, db_factory):
    _load_rule(db_session)
    db_session.add(Room(name=_BATHROOM_ROOM))
    db_session.commit()

    dispatcher = _FakeNotificationDispatcher()
    person_location = _make_person_location()
    services = _make_services(db_factory, dispatcher, person_location)
    engine = RulesEngine(services, tz_name="UTC")
    executor = PipelineExecutor(services, rules_engine=engine)
    call_count = _stub_llm(
        executor,
        {
            "same_outfit": False,
            "confidence": 0.2,
            "outfit_yesterday": "blue cardigan",
            "outfit_today": "green sweater",
            "reason": "different color and style",
        },
    )

    await executor.fire_event(source="cts", kind="dementia_signal", payload=_make_signal_payload())

    assert _signal_rows(db_session) == []
    assert call_count["llm_call"] == 1
    assert dispatcher.calls == []
