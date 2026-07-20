"""M12: rule context-filter subsystem repair -- through-engine tests.

Covers the C1/C2 headline regressions from
codebase-hardening-m12-cc-rule-filter-subsystem-repair.md:

- C1: async filter contexts (9 of 13 builtin filters are ``async def``) used
  to crash rule matching via ``run_until_complete`` on the running loop.
  Matching is now async end-to-end.
- C2: every context check used to pass ``services=None``, so CTS-aware
  filters always failed closed. The engine now holds the shared
  ``ServiceContainer`` and passes it to every filter evaluation.

Filters are exercised through ``RulesEngine.get_matching_rules`` /
``get_matching_rules_for_event`` (the real production entry points), never
by calling ``filter.evaluate()`` directly -- that is what makes these
"through-engine" rather than per-filter unit tests (those already exist
under this directory).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata
from backend.models.person import PersonActivity
from backend.models.rule import Rule, RuleContext
from backend.models.sensor import Sensor
from backend.services.cts.metrics import cts_filter_degraded_total
from backend.services.person_location.types import CurrentLocation, PresenceSegment
from backend.services.presence import PresenceSnapshot, PresenceStatus
from backend.services.rules_engine import RulesEngine
from backend.steps.base import ServiceContainer

FilterRegistry.discover()

_NOW = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)


def _make_sensor(db, sensor_id="cam1"):
    sensor = Sensor(id=sensor_id, name=sensor_id, sensor_type="camera", enabled=True)
    db.add(sensor)
    db.flush()
    return sensor


def _make_rule(db, name, *, contexts: list[RuleContext] | None = None, **kwargs):
    rule = Rule(
        name=name,
        enabled=True,
        trigger_types=kwargs.pop("trigger_types", ["sensor_event"]),
        cool_off_minutes=0,
        max_daily_triggers=0,
        **kwargs,
    )
    db.add(rule)
    db.flush()
    for ctx in contexts or []:
        ctx.rule_id = rule.id
        db.add(ctx)
    db.flush()
    return rule


def _ctx(context_type: str, config: dict, *, negate: bool = False) -> RuleContext:
    return RuleContext(context_type=context_type, config_json=config, negate=negate)


class _StubPersonLocationService:
    """Stub matching PersonLocationService's async surface used by filters."""

    def __init__(
        self,
        *,
        current: CurrentLocation | None = None,
        dwell_segment: PresenceSegment | None = None,
        history: list[PresenceSegment] | None = None,
    ) -> None:
        self._current = current
        self._dwell_segment = dwell_segment
        self._history = history or []

    async def where_is(self, person_id: str, at: datetime | None = None):
        return self._current

    async def current_dwell(self, person_id: str):
        return self._dwell_segment

    async def presence_history(self, person_id: str, *, since: datetime, until: datetime):
        return self._history


class _StubPresenceService:
    def __init__(self, snapshot: PresenceSnapshot | None = None) -> None:
        self._snapshot = snapshot

    async def get(self, person_id: str, *, at: datetime | None = None):
        if self._snapshot is not None:
            return self._snapshot
        return PresenceSnapshot(
            person_id=person_id,
            status=PresenceStatus.UNKNOWN,
            room_id=None,
            room_name=None,
            confidence=0.0,
            last_seen_at=None,
            dwell_minutes=None,
            sources=(),
            inferred_at=_NOW,
        )


def _location(room_id="k1", room_name="Kitchen") -> CurrentLocation:
    return CurrentLocation(
        person_id="mom",
        room_id=room_id,
        room_name=room_name,
        since=_NOW - timedelta(minutes=10),
        entry_source="observed",
        confidence=0.9,
        is_inferred=False,
        quality="high",
        last_observed_at=_NOW,
    )


def _segment(
    room_id="k1",
    room_name="Kitchen",
    entered_at: datetime | None = None,
    entry_source="observed",
    exit_source=None,
    superseded_by=None,
) -> PresenceSegment:
    return PresenceSegment(
        id=uuid4(),
        person_id="mom",
        room_id=room_id,
        entered_at=entered_at or (_NOW - timedelta(minutes=10)),
        exited_at=None,
        entry_source=entry_source,
        exit_source=exit_source,
        confidence=0.9,
        last_observed_at=_NOW,
        metadata={"room_name": room_name},
        superseded_by=superseded_by,
    )


class _StubSemanticMemoryClient:
    def __init__(self, transitions=None, recent_objects=None, search_hits=None) -> None:
        self._transitions = transitions or []
        self._recent_objects = recent_objects or []
        self._search_hits = search_hits or []

    async def get_transitions(self, person_id, *, semantic, to_room_id, since_minutes):
        return self._transitions

    async def get_recent_objects(self, room_id, *, since_minutes):
        return self._recent_objects

    async def search_observations(self, request):
        return self._search_hits


class _Transition:
    def __init__(self, confidence: float) -> None:
        self.confidence = confidence


class _RecentObject:
    def __init__(self, label: str, observation_count: int) -> None:
        self.label = label
        self.observation_count = observation_count


def _engine(**container_overrides) -> RulesEngine:
    return RulesEngine(
        ServiceContainer(db_factory=lambda: None, **container_overrides), tz_name="UTC"
    )


# ---------------------------------------------------------------------------
# C1 headline: async filter context no longer crashes matching
# ---------------------------------------------------------------------------


class TestC1AsyncMatchingRegression:
    async def test_async_room_context_matches_through_engine_on_running_loop(self, db_session):
        """Before M12: RulesEngine._matches_context bridged coroutines with
        asyncio.get_event_loop().run_until_complete(...), which raises
        RuntimeError when called from a coroutine already running on the
        event loop (every real production trigger path). This must not
        raise, and must produce the correct match, when awaited normally.
        """
        sensor = _make_sensor(db_session)
        rule = _make_rule(
            db_session,
            "Room-scoped rule",
            contexts=[_ctx("room", {"room_id": "k1", "person_id": "mom"})],
        )
        db_session.commit()

        engine = _engine(person_location=_StubPersonLocationService(current=_location("k1")))
        matched = await engine.get_matching_rules(sensor, db_session)
        assert [r.id for r in matched] == [rule.id]


# ---------------------------------------------------------------------------
# 13-filter through-engine matrix (C2 headline)
# ---------------------------------------------------------------------------


class TestFilterMatrixSensorPath:
    """Filters exercised via get_matching_rules (real Sensor subject).

    ``dementia_signal`` is exercised separately via get_matching_rules_for_event
    below: it requires a dict-shaped event subject by design (it is not in
    RulesEngine._SENSOR_DEPENDENT_FILTERS -- it simply never matches a real
    Sensor row, the same as production).
    """

    async def test_room(self, db_session):
        sensor = _make_sensor(db_session)
        match = _make_rule(
            db_session, "match", contexts=[_ctx("room", {"room_id": "k1", "person_id": "mom"})]
        )
        nomatch = _make_rule(
            db_session,
            "nomatch",
            contexts=[_ctx("room", {"room_id": "bathroom", "person_id": "mom"})],
        )
        db_session.commit()

        engine = _engine(person_location=_StubPersonLocationService(current=_location("k1")))
        matched = {r.id for r in await engine.get_matching_rules(sensor, db_session)}
        assert matched == {match.id}
        assert nomatch.id not in matched

    async def test_room_negated(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(
            db_session,
            "negated",
            contexts=[_ctx("room", {"room_id": "bathroom", "person_id": "mom"}, negate=True)],
        )
        db_session.commit()

        engine = _engine(person_location=_StubPersonLocationService(current=_location("k1")))
        matched = {r.id for r in await engine.get_matching_rules(sensor, db_session)}
        assert matched == {rule.id}

    async def test_time_range(self, db_session):
        sensor = _make_sensor(db_session)
        match = _make_rule(
            db_session,
            "match",
            contexts=[_ctx("time_range", {"start_time": "09:00", "end_time": "17:00"})],
        )
        nomatch = _make_rule(
            db_session,
            "nomatch",
            contexts=[_ctx("time_range", {"start_time": "18:00", "end_time": "23:00"})],
        )
        db_session.commit()

        import unittest.mock

        with unittest.mock.patch("backend.services.rules_engine.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW  # 12:00 UTC
            matched = {r.id for r in await _engine().get_matching_rules(sensor, db_session)}
        assert matched == {match.id}
        assert nomatch.id not in matched

    async def test_day_of_week(self, db_session):
        sensor = _make_sensor(db_session)
        today = _NOW.weekday()
        other_day = (today + 1) % 7
        match = _make_rule(db_session, "match", contexts=[_ctx("day_of_week", {"days": [today]})])
        nomatch = _make_rule(
            db_session, "nomatch", contexts=[_ctx("day_of_week", {"days": [other_day]})]
        )
        db_session.commit()

        import unittest.mock

        with unittest.mock.patch("backend.services.rules_engine.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW
            matched = {r.id for r in await _engine().get_matching_rules(sensor, db_session)}
        assert matched == {match.id}
        assert nomatch.id not in matched

    async def test_person_presence(self, db_session):
        sensor = _make_sensor(db_session)
        match = _make_rule(
            db_session,
            "match",
            contexts=[_ctx("person_presence", {"person_id": "mom", "status": "home"})],
        )
        nomatch = _make_rule(
            db_session,
            "nomatch",
            contexts=[_ctx("person_presence", {"person_id": "mom", "status": "away"})],
        )
        db_session.commit()

        engine = _engine(person_location=_StubPersonLocationService(current=_location("k1")))
        matched = {r.id for r in await engine.get_matching_rules(sensor, db_session)}
        assert matched == {match.id}
        assert nomatch.id not in matched

    async def test_person_activity(self, db_session):
        sensor = _make_sensor(db_session)
        from backend.models.person import HouseholdMember

        db_session.add(HouseholdMember(id="mom", name="Mom"))
        db_session.add(
            PersonActivity(
                person_id="mom",
                activity_type="eating",
                detected_at=_NOW - timedelta(minutes=5),
            )
        )
        match = _make_rule(
            db_session,
            "match",
            contexts=[
                _ctx(
                    "person_activity",
                    {"person_id": "mom", "activity_type": "eating", "within_minutes": 30},
                )
            ],
        )
        nomatch = _make_rule(
            db_session,
            "nomatch",
            contexts=[
                _ctx(
                    "person_activity",
                    {"person_id": "mom", "activity_type": "sleeping", "within_minutes": 30},
                )
            ],
        )
        db_session.commit()

        import unittest.mock

        with unittest.mock.patch("backend.services.rules_engine.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW
            matched = {r.id for r in await _engine().get_matching_rules(sensor, db_session)}
        assert matched == {match.id}
        assert nomatch.id not in matched

    async def test_room_transition(self, db_session):
        sensor = _make_sensor(db_session)
        history = [
            _segment(
                room_id="hallway", room_name="Hallway", entered_at=_NOW - timedelta(minutes=3)
            ),
            _segment(room_id="k1", room_name="Kitchen", entered_at=_NOW - timedelta(minutes=1)),
        ]
        match = _make_rule(
            db_session,
            "match",
            contexts=[_ctx("room_transition", {"person_id": "mom", "to_room_name": "Kitchen"})],
        )
        nomatch = _make_rule(
            db_session,
            "nomatch",
            contexts=[_ctx("room_transition", {"person_id": "mom", "to_room_name": "Bedroom"})],
        )
        db_session.commit()

        engine = _engine(person_location=_StubPersonLocationService(history=history))
        matched = {r.id for r in await engine.get_matching_rules(sensor, db_session)}
        assert matched == {match.id}
        assert nomatch.id not in matched

    async def test_person_movement_memory(self, db_session):
        sensor = _make_sensor(db_session)
        match = _make_rule(
            db_session,
            "match",
            contexts=[_ctx("person_movement_memory", {"person_id": "mom", "min_confidence": 0.5})],
        )
        nomatch = _make_rule(
            db_session,
            "nomatch",
            contexts=[_ctx("person_movement_memory", {"person_id": "mom", "min_confidence": 0.99})],
        )
        db_session.commit()

        engine = _engine(
            semantic_memory_client=_StubSemanticMemoryClient(transitions=[_Transition(0.8)])
        )
        matched = {r.id for r in await engine.get_matching_rules(sensor, db_session)}
        assert matched == {match.id}
        assert nomatch.id not in matched

    async def test_scene_contains(self, db_session):
        sensor = _make_sensor(db_session)
        match = _make_rule(
            db_session,
            "match",
            contexts=[_ctx("scene_contains", {"room_id": "k1", "objects_any": ["kettle"]})],
        )
        nomatch = _make_rule(
            db_session,
            "nomatch",
            contexts=[_ctx("scene_contains", {"room_id": "k1", "objects_any": ["knife"]})],
        )
        db_session.commit()

        engine = _engine(
            semantic_memory_client=_StubSemanticMemoryClient(
                recent_objects=[_RecentObject("kettle", 2)]
            )
        )
        matched = {r.id for r in await engine.get_matching_rules(sensor, db_session)}
        assert matched == {match.id}
        assert nomatch.id not in matched

    async def test_scene_trend(self, db_session):
        sensor = _make_sensor(db_session)
        match = _make_rule(
            db_session,
            "match",
            contexts=[
                _ctx(
                    "scene_trend",
                    {"person_id": "mom", "trend_type": "no_recent_activity", "within_minutes": 60},
                )
            ],
        )
        nomatch = _make_rule(
            db_session,
            "nomatch",
            contexts=[
                _ctx(
                    "scene_trend",
                    {"person_id": "someone_else", "trend_type": "no_recent_activity"},
                )
            ],
        )
        db_session.commit()

        # match: no history at all -> "no recent activity" is true.
        # nomatch rule targets a different person but shares the same stub
        # container (which has no history for anyone either) -- so to prove
        # a real negative we instead give the container an active segment
        # and assert the *match* rule flips to non-matching under it.
        engine_empty = _engine(person_location=_StubPersonLocationService(history=[]))
        matched = {r.id for r in await engine_empty.get_matching_rules(sensor, db_session)}
        assert match.id in matched

        engine_active = _engine(person_location=_StubPersonLocationService(history=[_segment()]))
        matched_active = {r.id for r in await engine_active.get_matching_rules(sensor, db_session)}
        assert match.id not in matched_active
        assert nomatch.id not in matched_active  # different person_id, never matches either way

    async def test_home_state(self, db_session):
        sensor = _make_sensor(db_session)
        match = _make_rule(
            db_session,
            "match",
            contexts=[_ctx("home_state", {"person_id": "mom", "state": "at_home"})],
        )
        nomatch = _make_rule(
            db_session,
            "nomatch",
            contexts=[_ctx("home_state", {"person_id": "mom", "state": "away"})],
        )
        db_session.commit()

        engine = _engine(person_location=_StubPersonLocationService(current=_location("k1")))
        matched = {r.id for r in await engine.get_matching_rules(sensor, db_session)}
        assert matched == {match.id}
        assert nomatch.id not in matched

    async def test_presence_status(self, db_session):
        sensor = _make_sensor(db_session)
        match = _make_rule(
            db_session,
            "match",
            contexts=[_ctx("presence_status", {"person_id": "mom", "status": "present_room"})],
        )
        nomatch = _make_rule(
            db_session,
            "nomatch",
            contexts=[_ctx("presence_status", {"person_id": "mom", "status": "away"})],
        )
        db_session.commit()

        engine = _engine(person_location=_StubPersonLocationService(current=_location("k1")))
        matched = {r.id for r in await engine.get_matching_rules(sensor, db_session)}
        assert matched == {match.id}
        assert nomatch.id not in matched

    async def test_presence_dwell(self, db_session):
        sensor = _make_sensor(db_session)
        segment = _segment(entered_at=_NOW - timedelta(minutes=20))
        match = _make_rule(
            db_session,
            "match",
            contexts=[_ctx("presence_dwell", {"person_id": "mom", "min_minutes": 10})],
        )
        nomatch = _make_rule(
            db_session,
            "nomatch",
            contexts=[_ctx("presence_dwell", {"person_id": "mom", "min_minutes": 60})],
        )
        db_session.commit()

        import unittest.mock

        engine = _engine(person_location=_StubPersonLocationService(dwell_segment=segment))
        with unittest.mock.patch("backend.services.rules_engine.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW
            matched = {r.id for r in await engine.get_matching_rules(sensor, db_session)}
        assert matched == {match.id}
        assert nomatch.id not in matched


class TestFilterMatrixEventPath:
    async def test_dementia_signal(self, db_session):
        match = _make_rule(
            db_session,
            "match",
            trigger_types=["dementia_signal"],
            contexts=[_ctx("dementia_signal", {"kinds": ["pacing"]})],
        )
        nomatch = _make_rule(
            db_session,
            "nomatch",
            trigger_types=["dementia_signal"],
            contexts=[_ctx("dementia_signal", {"kinds": ["absence"]})],
        )
        db_session.commit()

        event = {
            "kind": "dementia_signal",
            "payload": {"signal_kind": "pacing", "person_id": "mom", "severity": "warning"},
        }
        matched = {
            r.id
            for r in await _engine().get_matching_rules_for_event(
                event, "dementia_signal", db_session
            )
        }
        assert matched == {match.id}
        assert nomatch.id not in matched


# ---------------------------------------------------------------------------
# Fail-closed + degraded metric (C2)
# ---------------------------------------------------------------------------


class TestFailClosedMetric:
    async def test_room_fails_closed_and_increments_metric_when_unwired(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(
            db_session,
            "room rule",
            contexts=[_ctx("room", {"room_id": "k1", "person_id": "mom"})],
        )
        db_session.commit()

        before = cts_filter_degraded_total.labels(filter="room")._value.get()

        engine = _engine(person_location=None)
        matched = await engine.get_matching_rules(sensor, db_session)

        assert rule.id not in {r.id for r in matched}
        assert cts_filter_degraded_total.labels(filter="room")._value.get() == before + 1

    async def test_room_metric_does_not_move_when_wired(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(
            db_session,
            "room rule",
            contexts=[_ctx("room", {"room_id": "k1", "person_id": "mom"})],
        )
        db_session.commit()

        before = cts_filter_degraded_total.labels(filter="room")._value.get()

        engine = _engine(person_location=_StubPersonLocationService(current=_location("k1")))
        matched = await engine.get_matching_rules(sensor, db_session)

        assert rule.id in {r.id for r in matched}
        assert cts_filter_degraded_total.labels(filter="room")._value.get() == before


# ---------------------------------------------------------------------------
# Non-bool filter result -> TypeError naming the filter type
# ---------------------------------------------------------------------------


class _NonBoolFilter(ContextFilter):
    """Throwaway filter returning a non-bool, registered only for this test."""

    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="_test_non_bool",
            display_name="Test Non-Bool",
            description="Test-only filter returning a non-bool result.",
            config_schema={"type": "object", "properties": {}},
        )

    async def evaluate(self, config, sensor, now, db=None, services=None):
        return "not-a-bool"


class TestNonBoolFilterResult:
    async def test_raises_type_error_naming_filter(self, db_session):
        FilterRegistry.register(_NonBoolFilter)
        try:
            sensor = _make_sensor(db_session)
            _make_rule(db_session, "bad rule", contexts=[_ctx("_test_non_bool", {})])
            db_session.commit()

            with pytest.raises(TypeError, match="_test_non_bool"):
                await _engine().get_matching_rules(sensor, db_session)
        finally:
            del FilterRegistry._registry["_test_non_bool"]
            del FilterRegistry._instances["_test_non_bool"]


# ---------------------------------------------------------------------------
# Group semantics pin: OR within a context_type, AND across types
# ---------------------------------------------------------------------------


class TestGroupSemantics:
    async def test_or_within_same_context_type(self, db_session):
        """Two 'room' contexts on one rule: matching either is sufficient (OR)."""
        sensor = _make_sensor(db_session)
        rule = _make_rule(
            db_session,
            "or rule",
            contexts=[
                _ctx("room", {"room_id": "bathroom", "person_id": "mom"}),
                _ctx("room", {"room_id": "k1", "person_id": "mom"}),
            ],
        )
        db_session.commit()

        engine = _engine(person_location=_StubPersonLocationService(current=_location("k1")))
        matched = {r.id for r in await engine.get_matching_rules(sensor, db_session)}
        assert rule.id in matched

    async def test_and_across_different_context_types(self, db_session):
        """A 'room' context and a 'time_range' context: both must pass (AND)."""
        sensor = _make_sensor(db_session)
        rule_both_pass = _make_rule(
            db_session,
            "and rule pass",
            contexts=[
                _ctx("room", {"room_id": "k1", "person_id": "mom"}),
                _ctx("time_range", {"start_time": "09:00", "end_time": "17:00"}),
            ],
        )
        rule_one_fails = _make_rule(
            db_session,
            "and rule fail",
            contexts=[
                _ctx("room", {"room_id": "k1", "person_id": "mom"}),
                _ctx("time_range", {"start_time": "18:00", "end_time": "23:00"}),
            ],
        )
        db_session.commit()

        import unittest.mock

        engine = _engine(person_location=_StubPersonLocationService(current=_location("k1")))
        with unittest.mock.patch("backend.services.rules_engine.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW  # 12:00 UTC, inside 09:00-17:00
            matched = {r.id for r in await engine.get_matching_rules(sensor, db_session)}
        assert rule_both_pass.id in matched
        assert rule_one_fails.id not in matched
