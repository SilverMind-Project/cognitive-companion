"""DL-M04 Part E.4: end-to-end tests driving the daily-living TV/meal rule
bundles through the real RulesEngine (context filters) and PipelineExecutor
(step graph), with fake presence/HA state and a shared advanceable clock so
elapsed time -- not wall-clock sleep -- drives session duration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import backend.services.rules_engine as rules_engine_module
import backend.steps.builtin.activity_session_end as session_end_module
import backend.steps.builtin.activity_session_start as session_start_module
from backend.filters import FilterRegistry
from backend.schemas.rule_bundle import RuleBundle
from backend.services.activity import ActivityService
from backend.services.activity_session import ActivitySessionService
from backend.services.daily_report import DailyReportService
from backend.services.pipeline_executor import PipelineExecutor
from backend.services.rule_importer import bundle_to_rule
from backend.services.rules_engine import RulesEngine
from backend.steps import StepRegistry
from backend.steps.base import ServiceContainer, TriggerContext

StepRegistry.discover()
FilterRegistry.discover()

_BUNDLE_DIR = Path(__file__).resolve().parents[3] / "config" / "rule_bundles"

_PERSON_ID = "test_resident"
_TV_ROOM = "living_room"
_TV_ENTITY = "media_player.test_tv"
_DINING_ROOM = "dining_room"
_DINING_CAM = "test_dining_cam"

_PLACEHOLDERS = {
    "__RESIDENT_PERSON_ID__": _PERSON_ID,
    "__TV_ROOM_NAME__": _TV_ROOM,
    "__TV_MEDIA_PLAYER_ENTITY__": _TV_ENTITY,
    "__DINING_ROOM_NAME__": _DINING_ROOM,
    "__DINING_CAMERA_SENSOR_ID__": _DINING_CAM,
}


def _load_rule(db_session, filename: str):
    raw = (_BUNDLE_DIR / filename).read_text()
    for placeholder, value in _PLACEHOLDERS.items():
        raw = raw.replace(placeholder, value)
    bundle = RuleBundle(**json.loads(raw))
    report = bundle_to_rule(bundle, db_session, app_version="test")
    assert report.status == "ok", report.errors
    db_session.commit()
    from backend.models.rule import Rule

    return db_session.get(Rule, report.rule_id)


class _FakeClock(datetime):
    """Shared, advanceable ``now()`` patched into three modules at once."""

    _instant: datetime = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls._instant if tz is None else cls._instant.astimezone(tz)

    @classmethod
    def advance(cls, minutes: float) -> None:
        cls._instant = cls._instant + timedelta(minutes=minutes)


@pytest.fixture
def fake_clock(monkeypatch):
    _FakeClock._instant = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(rules_engine_module, "datetime", _FakeClock)
    monkeypatch.setattr(session_start_module, "datetime", _FakeClock)
    monkeypatch.setattr(session_end_module, "datetime", _FakeClock)
    return _FakeClock


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
        self.inferred_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


class _FakePresenceService:
    def __init__(self) -> None:
        self.snapshot = _FakeSnapshot(status="present_room", room_name=_TV_ROOM, dwell_minutes=0.0)

    async def get(self, person_id: str, *, at=None):
        return self.snapshot


@dataclass
class _FakeHaState:
    state: str


class _FakeHaStateCache:
    def __init__(self) -> None:
        self.states: dict[str, str] = {}

    def get(self, entity_id: str):
        state = self.states.get(entity_id)
        return _FakeHaState(state) if state is not None else None


class _FakePersonActivity:
    def __init__(self, **kwargs) -> None:
        self.id = 1
        self.room_id = None
        self.session_id = None
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakePersonTracking:
    """Stands in for the wired PersonTrackingService's record_activity.

    In production this is always wired (person_tracking is ALWAYS_REQUIRED
    on the container); stubbed here just so activity_session_end's optional
    write_activity_record=True path succeeds instead of logging a caught
    AttributeError on every tick.
    """

    async def record_activity(self, **kwargs):
        return _FakePersonActivity(detected_at=_FakeClock.now(UTC), **kwargs)


def _make_services(db_factory) -> ServiceContainer:
    activity_session = ActivitySessionService(db_factory)
    activity = ActivityService(
        person_tracking=_FakePersonTracking(), activity_session=activity_session
    )
    return ServiceContainer(
        db_factory=db_factory,
        activity=activity,
        presence=_FakePresenceService(),
        ha_state_cache=_FakeHaStateCache(),
    )


def _trigger() -> TriggerContext:
    return TriggerContext(trigger_type="cron")


async def _tick(rule, db_session, engine, executor):
    """One cron firing: filters gate, then (if they pass) run the step graph."""
    should_fire = await engine.get_matching_rules_for_cron(rule, db_session)
    if not should_fire:
        return None
    return await executor.execute(rule, _trigger(), db_session)


def _open_sessions(db_session, activity_type: str) -> list:
    from backend.models.person import ActivitySession

    # ActivitySessionService/ActivityService write through their own,
    # separate db_factory()-derived sessions (real connections against the
    # testcontainer, not a shared savepoint). expire_all() forces this
    # session's identity map to re-read rather than return objects cached
    # from an earlier call in the same test.
    db_session.expire_all()
    return (
        db_session.query(ActivitySession)
        .filter(
            ActivitySession.person_id == _PERSON_ID,
            ActivitySession.activity_type == activity_type,
        )
        .all()
    )


class TestTvOpenClose:
    async def test_tv_open_close_produces_one_session_with_duration(
        self, db_session, db_factory, fake_clock
    ):
        open_rule = _load_rule(db_session, "daily_living_tv_open.json")
        close_rule = _load_rule(db_session, "daily_living_tv_close.json")

        services = _make_services(db_factory)
        services.ha_state_cache.states[_TV_ENTITY] = "playing"
        engine = RulesEngine(services, tz_name="UTC")
        executor = PipelineExecutor(services)

        # Tick 1: TV on, present -> opens.
        await _tick(open_rule, db_session, engine, executor)
        await _tick(close_rule, db_session, engine, executor)

        sessions = _open_sessions(db_session, "watching_tv")
        assert len(sessions) == 1
        assert sessions[0].status == "open"

        # 30 minutes pass, she is still watching.
        fake_clock.advance(30)
        await _tick(open_rule, db_session, engine, executor)  # idempotent, no dup
        await _tick(close_rule, db_session, engine, executor)  # TV still on, no close

        sessions = _open_sessions(db_session, "watching_tv")
        assert len(sessions) == 1
        assert sessions[0].status == "open"

        # She turns the TV off.
        fake_clock.advance(1)
        services.ha_state_cache.states[_TV_ENTITY] = "off"
        await _tick(close_rule, db_session, engine, executor)

        sessions = _open_sessions(db_session, "watching_tv")
        assert len(sessions) == 1
        assert sessions[0].status == "closed"
        assert sessions[0].duration_minutes == pytest.approx(31, abs=1)
        assert sessions[0].metadata_json["source"] == "ha_state_join"

    async def test_tv_absence_closes_after_idle_minutes(self, db_session, db_factory, fake_clock):
        open_rule = _load_rule(db_session, "daily_living_tv_open.json")
        close_rule = _load_rule(db_session, "daily_living_tv_close.json")

        services = _make_services(db_factory)
        services.ha_state_cache.states[_TV_ENTITY] = "playing"
        engine = RulesEngine(services, tz_name="UTC")
        executor = PipelineExecutor(services)

        await _tick(open_rule, db_session, engine, executor)
        assert len(_open_sessions(db_session, "watching_tv")) == 1

        # TV stays on, but she leaves the room. Brief absence (< idle_close)
        # must not close the session yet.
        services.presence.snapshot.room_name = "kitchen"
        services.presence.snapshot.dwell_minutes = 4.0
        await _tick(close_rule, db_session, engine, executor)
        assert _open_sessions(db_session, "watching_tv")[0].status == "open"

        # She has now been in the kitchen for >= idle_close_minutes (10).
        services.presence.snapshot.dwell_minutes = 11.0
        fake_clock.advance(11)
        await _tick(close_rule, db_session, engine, executor)
        assert _open_sessions(db_session, "watching_tv")[0].status == "closed"


class TestMealSessions:
    async def test_meal_two_sittings_within_gap_is_one_session(
        self, db_session, db_factory, fake_clock, monkeypatch
    ):
        open_rule = _load_rule(db_session, "daily_living_meal_open.json")
        close_rule = _load_rule(db_session, "daily_living_meal_close.json")

        services = _make_services(db_factory)
        services.presence.snapshot.room_name = _DINING_ROOM
        services.presence.snapshot.dwell_minutes = 3.0
        engine = RulesEngine(services, tz_name="UTC")
        executor = PipelineExecutor(services)

        # Stub only the vision steps; let condition/activity_session_start run for real.
        original = executor._execute_step

        async def _patched(step, execution, pipeline_data, trigger):
            from backend.steps.base import StepResult

            if step.step_type == "media_window_poll":
                return StepResult(data={})
            if step.step_type == "scene_analysis":
                return StepResult(data={"scene_description": "a person eating a meal at a table"})
            return await original(step, execution, pipeline_data, trigger)

        monkeypatch.setattr(executor, "_execute_step", _patched)

        # First sitting.
        await _tick(open_rule, db_session, engine, executor)
        assert len(_open_sessions(db_session, "meal_eating")) == 1

        # Brief bathroom break: absent for less than merge_gap_minutes (20).
        services.presence.snapshot.room_name = "bathroom"
        services.presence.snapshot.dwell_minutes = 5.0
        fake_clock.advance(5)
        await _tick(close_rule, db_session, engine, executor)
        assert _open_sessions(db_session, "meal_eating")[0].status == "open"

        # Re-seated at the table -> idempotent reuse of the same session.
        services.presence.snapshot.room_name = _DINING_ROOM
        services.presence.snapshot.dwell_minutes = 3.0
        fake_clock.advance(3)
        await _tick(open_rule, db_session, engine, executor)
        assert len(_open_sessions(db_session, "meal_eating")) == 1

        # Finishes and leaves for good, past the merge gap.
        services.presence.snapshot.room_name = "living_room_other"
        services.presence.snapshot.dwell_minutes = 21.0
        fake_clock.advance(21)
        await _tick(close_rule, db_session, engine, executor)

        sessions = _open_sessions(db_session, "meal_eating")
        assert len(sessions) == 1
        assert sessions[0].status == "closed"

    async def test_meal_after_gap_is_two_sessions(
        self, db_session, db_factory, fake_clock, monkeypatch
    ):
        open_rule = _load_rule(db_session, "daily_living_meal_open.json")
        close_rule = _load_rule(db_session, "daily_living_meal_close.json")

        services = _make_services(db_factory)
        services.presence.snapshot.room_name = _DINING_ROOM
        services.presence.snapshot.dwell_minutes = 3.0
        engine = RulesEngine(services, tz_name="UTC")
        executor = PipelineExecutor(services)

        original = executor._execute_step

        async def _patched(step, execution, pipeline_data, trigger):
            from backend.steps.base import StepResult

            if step.step_type == "media_window_poll":
                return StepResult(data={})
            if step.step_type == "scene_analysis":
                return StepResult(data={"scene_description": "a person eating a meal at a table"})
            return await original(step, execution, pipeline_data, trigger)

        monkeypatch.setattr(executor, "_execute_step", _patched)

        # Breakfast.
        await _tick(open_rule, db_session, engine, executor)
        services.presence.snapshot.room_name = "living_room_other"
        services.presence.snapshot.dwell_minutes = 21.0
        fake_clock.advance(21)
        await _tick(close_rule, db_session, engine, executor)
        assert len(_open_sessions(db_session, "meal_eating")) == 1
        assert _open_sessions(db_session, "meal_eating")[0].status == "closed"

        # Hours later: lunch. A brand new session, not a reuse of breakfast.
        fake_clock.advance(240)
        services.presence.snapshot.room_name = _DINING_ROOM
        services.presence.snapshot.dwell_minutes = 3.0
        await _tick(open_rule, db_session, engine, executor)

        sessions = _open_sessions(db_session, "meal_eating")
        assert len(sessions) == 2
        assert sessions[1].status == "open"

    async def test_meal_non_food_caption_opens_no_session(
        self, db_session, db_factory, fake_clock, monkeypatch
    ):
        """A dining-room presence tick whose caption never mentions food must
        not open a meal session -- the Florence-2 keyword condition, not mere
        room presence, is what gates the meal-open rule."""
        open_rule = _load_rule(db_session, "daily_living_meal_open.json")

        services = _make_services(db_factory)
        services.presence.snapshot.room_name = _DINING_ROOM
        services.presence.snapshot.dwell_minutes = 3.0
        engine = RulesEngine(services, tz_name="UTC")
        executor = PipelineExecutor(services)

        original = executor._execute_step

        async def _patched(step, execution, pipeline_data, trigger):
            from backend.steps.base import StepResult

            if step.step_type == "media_window_poll":
                return StepResult(data={})
            if step.step_type == "scene_analysis":
                return StepResult(data={"scene_description": "a person reading at a table"})
            return await original(step, execution, pipeline_data, trigger)

        monkeypatch.setattr(executor, "_execute_step", _patched)

        await _tick(open_rule, db_session, engine, executor)
        assert _open_sessions(db_session, "meal_eating") == []


class TestDailyReportAggregation:
    """DL-M04 Part E.4 headline: the rule-driven sessions above must be what
    the daily report actually counts -- not just correct as session rows.
    ``get_daily_report``/``get_person_timeline`` are the only interfaces the
    voice agent uses (DL2); a session dedup bug that never reaches the
    aggregator would be invisible to "how many times did she eat today."
    """

    async def test_tv_session_reflected_in_daily_report_minutes(
        self, db_session, db_factory, fake_clock
    ):
        open_rule = _load_rule(db_session, "daily_living_tv_open.json")
        close_rule = _load_rule(db_session, "daily_living_tv_close.json")

        services = _make_services(db_factory)
        services.ha_state_cache.states[_TV_ENTITY] = "playing"
        engine = RulesEngine(services, tz_name="UTC")
        executor = PipelineExecutor(services)

        await _tick(open_rule, db_session, engine, executor)
        await _tick(close_rule, db_session, engine, executor)

        fake_clock.advance(45)
        services.ha_state_cache.states[_TV_ENTITY] = "off"
        await _tick(close_rule, db_session, engine, executor)
        assert _open_sessions(db_session, "watching_tv")[0].status == "closed"

        report_service = DailyReportService(db_factory)
        report = await report_service.generate_daily_report(_PERSON_ID, "2026-06-01", tz_name="UTC")

        assert report["tv"]["session_count"] == 1
        assert report["tv"]["total_minutes"] == pytest.approx(45, abs=1)

    async def test_merged_meal_sitting_counts_as_one_eating_session_in_report(
        self, db_session, db_factory, fake_clock, monkeypatch
    ):
        open_rule = _load_rule(db_session, "daily_living_meal_open.json")
        close_rule = _load_rule(db_session, "daily_living_meal_close.json")

        services = _make_services(db_factory)
        services.presence.snapshot.room_name = _DINING_ROOM
        services.presence.snapshot.dwell_minutes = 3.0
        engine = RulesEngine(services, tz_name="UTC")
        executor = PipelineExecutor(services)

        original = executor._execute_step

        async def _patched(step, execution, pipeline_data, trigger):
            from backend.steps.base import StepResult

            if step.step_type == "media_window_poll":
                return StepResult(data={})
            if step.step_type == "scene_analysis":
                return StepResult(data={"scene_description": "a person eating a meal at a table"})
            return await original(step, execution, pipeline_data, trigger)

        monkeypatch.setattr(executor, "_execute_step", _patched)

        # Two sittings within the merge gap -- must dedup to one session, and
        # that dedup must survive into the report's eating_count.
        await _tick(open_rule, db_session, engine, executor)
        services.presence.snapshot.room_name = "bathroom"
        services.presence.snapshot.dwell_minutes = 5.0
        fake_clock.advance(5)
        await _tick(close_rule, db_session, engine, executor)

        services.presence.snapshot.room_name = _DINING_ROOM
        services.presence.snapshot.dwell_minutes = 3.0
        fake_clock.advance(3)
        await _tick(open_rule, db_session, engine, executor)

        services.presence.snapshot.room_name = "living_room_other"
        services.presence.snapshot.dwell_minutes = 21.0
        fake_clock.advance(21)
        await _tick(close_rule, db_session, engine, executor)
        assert _open_sessions(db_session, "meal_eating")[0].status == "closed"

        report_service = DailyReportService(db_factory)
        report = await report_service.generate_daily_report(_PERSON_ID, "2026-06-01", tz_name="UTC")

        assert report["meals"]["eating_count"] == 1
