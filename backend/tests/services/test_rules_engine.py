"""Tests for RulesEngine  rule matching, rate limits, and context filtering."""

from __future__ import annotations

import unittest.mock
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from backend.filters import FilterRegistry
from backend.models.event import EventLog
from backend.models.rule import Rule, RuleContext, RuleDependency
from backend.models.sensor import Sensor
from backend.services.rules_engine import RulesEngine
from backend.steps.base import ServiceContainer

# Ensure built-in context filters are registered for the test suite.
# In production this is triggered by main.py's lifespan; tests must do it explicitly.
FilterRegistry.discover()


def _make_sensor(db, sensor_id="cam1", sensor_type="camera"):
    sensor = Sensor(id=sensor_id, name=sensor_id, sensor_type=sensor_type, enabled=True)
    db.add(sensor)
    db.flush()
    return sensor


def _make_rule(db, name="Test Rule", trigger_types=None, **kwargs):
    rule = Rule(
        name=name,
        enabled=True,
        trigger_types=trigger_types if trigger_types is not None else ["sensor_event"],
        # Default to 0 so tests don't accidentally trigger built-in rate limits
        cool_off_minutes=kwargs.pop("cool_off_minutes", 0),
        max_daily_triggers=kwargs.pop("max_daily_triggers", 0),
        **kwargs,
    )
    db.add(rule)
    db.flush()
    return rule


def _log_completed(db, rule, minutes_ago=0):
    """Insert a completed EventLog entry for *rule*, *minutes_ago* minutes in the past.

    Timestamps are always written as aware UTC datetimes.
    """
    ts = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    log = EventLog(
        rule_id=rule.id,
        rule_name=rule.name,
        sensor_id="cam1",
        trigger_type="sensor_event",
        status="completed",
        timestamp=ts,
    )
    db.add(log)
    db.flush()
    return log


def _services(**overrides) -> ServiceContainer:
    return ServiceContainer(db_factory=lambda: None, **overrides)


def _engine_utc(**services_overrides) -> RulesEngine:
    """Return a RulesEngine using UTC so timestamp comparisons are consistent
    with the UTC datetimes stored by ``_log_completed`` in the test DB."""
    return RulesEngine(_services(**services_overrides), tz_name="UTC")


class TestRulesEngineBasicMatching:
    async def test_enabled_rule_matches(self, db_session):
        sensor = _make_sensor(db_session)
        _make_rule(db_session)
        db_session.commit()

        matched = await _engine_utc().get_matching_rules(sensor, db_session)
        assert len(matched) == 1

    async def test_disabled_rule_not_matched(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session)
        rule.enabled = False
        db_session.commit()

        matched = await _engine_utc().get_matching_rules(sensor, db_session)
        assert matched == []

    async def test_wrong_trigger_type_not_matched(self, db_session):
        sensor = _make_sensor(db_session)
        _make_rule(db_session, trigger_types=["cron"])
        db_session.commit()

        matched = await _engine_utc().get_matching_rules(
            sensor, db_session, trigger_type="sensor_event"
        )
        assert matched == []

    async def test_multiple_rules_all_matched(self, db_session):
        sensor = _make_sensor(db_session)
        _make_rule(db_session, name="Rule A")
        _make_rule(db_session, name="Rule B")
        db_session.commit()

        matched = await _engine_utc().get_matching_rules(sensor, db_session)
        assert len(matched) == 2


class TestRulesEngineRateLimits:
    async def test_cool_off_blocks_recent_completion(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session, cool_off_minutes=60)
        _log_completed(db_session, rule, minutes_ago=5)  # fired 5 min ago
        db_session.commit()

        matched = await _engine_utc().get_matching_rules(sensor, db_session)
        assert matched == []

    async def test_cool_off_allows_after_window(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session, cool_off_minutes=10)
        _log_completed(db_session, rule, minutes_ago=15)  # fired 15 min ago
        db_session.commit()

        matched = await _engine_utc().get_matching_rules(sensor, db_session)
        assert len(matched) == 1

    async def test_max_daily_triggers_blocks_at_limit(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session, max_daily_triggers=3)

        # Use a fixed reference time safely in the middle of a day to avoid
        # midnight-boundary flakiness when the wall clock crosses a day.
        now = datetime.now(UTC)
        ref_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if ref_time > now:
            ref_time = ref_time - timedelta(days=1)

        # Create 3 completed EventLogs at ref_time - 30 min (same day).
        for _ in range(3):
            ts = ref_time - timedelta(minutes=30)
            log = EventLog(
                rule_id=rule.id,
                rule_name=rule.name,
                sensor_id="cam1",
                trigger_type="sensor_event",
                status="completed",
                timestamp=ts,
            )
            db_session.add(log)
        db_session.commit()

        # Patch datetime.now so the engine's internal "now" matches ref_time.
        with unittest.mock.patch("backend.services.rules_engine.datetime") as mock_dt:
            mock_dt.now.return_value = ref_time
            matched = await _engine_utc().get_matching_rules(sensor, db_session)
        assert matched == []

    async def test_max_daily_triggers_allows_below_limit(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session, max_daily_triggers=5)
        for _ in range(3):
            _log_completed(db_session, rule, minutes_ago=30)
        db_session.commit()

        matched = await _engine_utc().get_matching_rules(sensor, db_session)
        assert len(matched) == 1

    async def test_zero_cool_off_never_blocks(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session, cool_off_minutes=0)
        _log_completed(db_session, rule, minutes_ago=0)
        db_session.commit()

        matched = await _engine_utc().get_matching_rules(sensor, db_session)
        assert len(matched) == 1


class TestRulesEngineDependencies:
    async def test_require_success_passes_when_parent_completed(self, db_session):
        sensor = _make_sensor(db_session)
        parent = _make_rule(db_session, name="Parent")
        child = _make_rule(db_session, name="Child")

        dep = RuleDependency(
            dependent_rule_id=child.id,
            parent_rule_id=parent.id,
            require_success=True,
            lookback_minutes=60,
        )
        db_session.add(dep)
        _log_completed(db_session, parent, minutes_ago=10)
        db_session.commit()

        matched = await _engine_utc().get_matching_rules(sensor, db_session)
        matched_names = {r.name for r in matched}
        assert "Child" in matched_names

    async def test_require_success_fails_when_parent_not_completed(self, db_session):
        sensor = _make_sensor(db_session)
        parent = _make_rule(db_session, name="Parent")
        child = _make_rule(db_session, name="Child")

        dep = RuleDependency(
            dependent_rule_id=child.id,
            parent_rule_id=parent.id,
            require_success=True,
            lookback_minutes=60,
        )
        db_session.add(dep)
        # No completed log for parent
        db_session.commit()

        matched = await _engine_utc().get_matching_rules(sensor, db_session)
        matched_names = {r.name for r in matched}
        assert "Child" not in matched_names


class TestRulesEngineContextFilters:
    async def test_unknown_context_type_does_not_filter(self, db_session):
        """Unknown filter types should fall through (return True) to avoid
        accidentally blocking rules when a plugin isn't loaded."""
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session)
        ctx = RuleContext(
            rule_id=rule.id,
            context_type="nonexistent_filter",
            config_json={},
        )
        db_session.add(ctx)
        db_session.commit()

        matched = await _engine_utc().get_matching_rules(sensor, db_session)
        assert len(matched) == 1

    async def test_negated_unknown_context_still_allows_rule(self, db_session):
        """Negating an unknown context type keeps the rule allowed.

        ``_matches_context`` returns True for unknown filter types regardless of
        the ``negate`` flag because the fall-through path (after the registry
        miss) always returns True.  This is intentional: unknown filters must
        never silently block rules.
        """
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session)
        ctx = RuleContext(
            rule_id=rule.id,
            context_type="nonexistent_filter",
            config_json={},
            negate=True,
        )
        db_session.add(ctx)
        db_session.commit()

        matched = await _engine_utc().get_matching_rules(sensor, db_session)
        # Unknown filter always passes (negate is ignored for unresolved types)
        assert len(matched) == 1


# ---------------------------------------------------------------------------
# Timezone-aware rate limits
# ---------------------------------------------------------------------------


class TestTimezoneAwareLimits:
    """Verify that rate-limit windows respect the configured local timezone.

    The key invariant: ``max_daily_triggers`` resets at *local midnight*
    (the calendar-day boundary in the configured timezone), not at UTC
    midnight.  Tests use America/New_York (UTC-5 / UTC-4 DST) because the
    5-hour offset creates a noticeable gap between local and UTC midnights.
    """

    _TZ_NY = "America/New_York"

    def _engine_ny(self) -> RulesEngine:
        return RulesEngine(_services(), tz_name=self._TZ_NY)

    def _log_utc(self, db, rule, utc_dt: datetime):
        """Insert a completed EventLog at an explicit UTC datetime."""
        log = EventLog(
            rule_id=rule.id,
            rule_name=rule.name,
            sensor_id="cam1",
            trigger_type="sensor_event",
            status="completed",
            timestamp=utc_dt,
        )
        db.add(log)
        db.flush()
        return log

    def test_daily_limit_uses_local_midnight_not_utc(self, db_session):
        """An event at 23:30 UTC (which is 18:30 ET) must NOT count toward
        tomorrow's local-day limit when 'now' is 01:00 ET the next calendar day.

        Without the fix (using UTC midnight), both timestamps fall on the same
        UTC day, so the count would incorrectly include yesterday's 23:30 UTC
        event.  With the fix, local midnight separates them correctly.
        """
        _make_sensor(db_session)
        rule = _make_rule(db_session, max_daily_triggers=1)

        # An event at 2024-01-15 23:30 UTC = 2024-01-15 18:30 ET (yesterday ET)
        past_utc = datetime(2024, 1, 15, 23, 30, 0, tzinfo=UTC)
        self._log_utc(db_session, rule, past_utc)
        db_session.commit()

        # "Now" is 2024-01-16 01:00 ET = 2024-01-16 06:00 UTC (next local day)
        now_et = datetime(2024, 1, 16, 1, 0, 0, tzinfo=ZoneInfo(self._TZ_NY))

        engine = self._engine_ny()
        # Directly test _check_rate_limits since get_matching_rules builds 'now' internally.
        result = engine._check_rate_limits(rule, db_session, now_et)
        # The past event is on the previous ET calendar day, so today's count = 0.
        assert result is True, (
            "Daily limit should not be triggered: event was on a previous local calendar day"
        )

    def test_daily_limit_counts_events_after_local_midnight(self, db_session):
        """Events after local midnight must count toward today's local limit."""
        _make_sensor(db_session)
        rule = _make_rule(db_session, max_daily_triggers=2)

        # Two events today in ET: 01:00 ET and 03:00 ET
        tz = ZoneInfo(self._TZ_NY)
        now_et = datetime(2024, 1, 16, 10, 0, 0, tzinfo=tz)
        for hour in (1, 3):
            self._log_utc(db_session, rule, datetime(2024, 1, 16, hour + 5, 0, tzinfo=UTC))
        db_session.commit()

        engine = self._engine_ny()
        result = engine._check_rate_limits(rule, db_session, now_et)
        # count == max → should block
        assert result is False, "Daily limit (2/2) should block the rule"

    def test_cool_off_is_timezone_agnostic(self, db_session):
        """Cool-off is a relative window (N minutes back from now): it should
        work the same regardless of timezone because it uses elapsed UTC time."""
        _make_sensor(db_session)
        rule = _make_rule(db_session, cool_off_minutes=30)

        # Event 10 minutes ago UTC
        recent_utc = datetime.now(UTC) - timedelta(minutes=10)
        log = EventLog(
            rule_id=rule.id,
            rule_name=rule.name,
            sensor_id="cam1",
            trigger_type="sensor_event",
            status="completed",
            timestamp=recent_utc,
        )
        db_session.add(log)
        db_session.commit()

        # Test with America/New_York engine: cool-off should still trigger
        engine = self._engine_ny()
        now_et = datetime.now(ZoneInfo(self._TZ_NY))
        result = engine._check_rate_limits(rule, db_session, now_et)
        assert result is False, "Cool-off within window should block the rule"


# ---------------------------------------------------------------------------
# Time-range context filter with non-UTC timezone
# ---------------------------------------------------------------------------


class TestTimeRangeContextFilter:
    """Verify that the time_range filter works correctly with a local timezone."""

    _TZ_NY = "America/New_York"

    def _engine_ny(self) -> RulesEngine:
        return RulesEngine(_services(), tz_name=self._TZ_NY)

    async def test_time_range_matches_local_time(self, db_session):
        """A time_range filter should fire when local time is inside the window,
        even when that local window straddles midnight UTC."""
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session)
        ctx = RuleContext(
            rule_id=rule.id,
            context_type="time_range",
            config_json={"start_time": "22:00", "end_time": "23:59"},
        )
        db_session.add(ctx)
        db_session.commit()

        # 23:00 ET = 04:00 UTC next day → inside window in ET, outside in UTC
        now_et = datetime(2024, 1, 16, 23, 0, 0, tzinfo=ZoneInfo(self._TZ_NY))
        engine = self._engine_ny()
        # Call _check_contexts directly so we can supply our fixed 'now'.
        result = await engine._check_contexts(rule, sensor, now_et, db_session, "sensor")
        assert result is True, "23:00 ET should match 22:00-23:59 ET window"

    async def test_time_range_blocks_outside_local_window(self, db_session):
        """A time_range filter should NOT fire when local time is outside window."""
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session)
        ctx = RuleContext(
            rule_id=rule.id,
            context_type="time_range",
            config_json={"start_time": "09:00", "end_time": "17:00"},
        )
        db_session.add(ctx)
        db_session.commit()

        # 20:00 ET (outside 09:00-17:00)
        now_et = datetime(2024, 1, 16, 20, 0, 0, tzinfo=ZoneInfo(self._TZ_NY))
        engine = self._engine_ny()
        result = await engine._check_contexts(rule, sensor, now_et, db_session, "sensor")
        assert result is False, "20:00 ET should not match 09:00-17:00 ET window"

    async def test_time_range_overnight_wraps_correctly(self, db_session):
        """An overnight window like 22:00-06:00 should match at 23:30 ET."""
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session)
        ctx = RuleContext(
            rule_id=rule.id,
            context_type="time_range",
            config_json={"start_time": "22:00", "end_time": "06:00"},
        )
        db_session.add(ctx)
        db_session.commit()

        now_et = datetime(2024, 1, 16, 23, 30, 0, tzinfo=ZoneInfo(self._TZ_NY))
        engine = self._engine_ny()
        result = await engine._check_contexts(rule, sensor, now_et, db_session, "sensor")
        assert result is True, "23:30 ET should match overnight 22:00-06:00 window"


# ---------------------------------------------------------------------------
# get_matching_rules_for_event (dementia signal dispatch)
# ---------------------------------------------------------------------------


class TestGetMatchingRulesForEvent:
    async def test_matches_rule_with_dementia_signal_trigger_type(self, db_session):
        rule = _make_rule(db_session, trigger_types=["dementia_signal"])
        engine = _engine_utc()
        event = {
            "kind": "dementia_signal",
            "payload": {"signal_kind": "pacing", "person_id": "grandma", "severity": "warning"},
        }
        matched = await engine.get_matching_rules_for_event(event, "dementia_signal", db_session)
        assert len(matched) == 1
        assert matched[0].id == rule.id

    async def test_excludes_rules_with_other_trigger_types(self, db_session):
        _make_rule(db_session, name="sensor-rule", trigger_types=["sensor_event"])
        engine = _engine_utc()
        event = {"kind": "dementia_signal", "payload": {}}
        matched = await engine.get_matching_rules_for_event(event, "dementia_signal", db_session)
        assert matched == []

    async def test_excludes_disabled_rules(self, db_session):
        rule = _make_rule(db_session, trigger_types=["dementia_signal"])
        rule.enabled = False
        db_session.commit()
        engine = _engine_utc()
        event = {"kind": "dementia_signal", "payload": {}}
        matched = await engine.get_matching_rules_for_event(event, "dementia_signal", db_session)
        assert matched == []

    async def test_dementia_signal_filter_evaluated_against_event(self, db_session):
        rule = _make_rule(db_session, trigger_types=["dementia_signal"])
        ctx = RuleContext(
            rule_id=rule.id,
            context_type="dementia_signal",
            config_json={"kinds": ["pacing"]},
        )
        db_session.add(ctx)
        db_session.commit()

        engine = _engine_utc()

        # pacing event matches
        pacing_event = {
            "kind": "dementia_signal",
            "payload": {"signal_kind": "pacing", "person_id": "grandma", "severity": "warning"},
        }
        assert await engine.get_matching_rules_for_event(
            pacing_event, "dementia_signal", db_session
        )

        # absence event does not match
        absence_event = {
            "kind": "dementia_signal",
            "payload": {"signal_kind": "absence", "person_id": "grandma", "severity": "warning"},
        }
        assert not await engine.get_matching_rules_for_event(
            absence_event, "dementia_signal", db_session
        )

    async def test_room_filter_is_skipped_for_event(self, db_session):
        """Room filter requires a Sensor ORM row; it must be skipped without error."""
        rule = _make_rule(db_session, trigger_types=["dementia_signal"])
        ctx = RuleContext(
            rule_id=rule.id,
            context_type="room",
            config_json={"room_name": "bedroom"},
        )
        db_session.add(ctx)
        db_session.commit()

        engine = _engine_utc()
        event = {"kind": "dementia_signal", "payload": {}}
        # Should not raise, and should still match (room filter skipped)
        matched = await engine.get_matching_rules_for_event(event, "dementia_signal", db_session)
        assert len(matched) == 1
