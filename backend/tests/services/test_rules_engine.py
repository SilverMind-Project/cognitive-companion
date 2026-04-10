"""Tests for RulesEngine  rule matching, rate limits, and context filtering."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.models.event import EventLog
from backend.models.rule import Rule, RuleContext, RuleDependency
from backend.models.sensor import Sensor
from backend.services.rules_engine import RulesEngine


def _make_sensor(db, sensor_id="cam1", sensor_type="camera"):
    sensor = Sensor(id=sensor_id, name=sensor_id, sensor_type=sensor_type, enabled=True)
    db.add(sensor)
    db.flush()
    return sensor


def _make_rule(db, name="Test Rule", trigger_type="sensor_event", **kwargs):
    rule = Rule(
        name=name,
        enabled=True,
        trigger_type=trigger_type,
        # Default to 0 so tests don't accidentally trigger built-in rate limits
        cool_off_minutes=kwargs.get("cool_off_minutes", 0),
        max_daily_triggers=kwargs.get("max_daily_triggers", 0),
    )
    db.add(rule)
    db.flush()
    return rule


def _log_completed(db, rule, minutes_ago=0):
    """Insert a completed EventLog entry for *rule*, *minutes_ago* minutes in the past.

    Timestamps are stored as UTC so SQLite string comparison works correctly
    with a UTC-based RulesEngine.
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


def _engine_utc() -> RulesEngine:
    """Return a RulesEngine using UTC so timestamp comparisons are consistent
    with the UTC datetimes stored by ``_log_completed`` in the test DB."""
    return RulesEngine(tz_name="UTC")


class TestRulesEngineBasicMatching:
    def test_enabled_rule_matches(self, db_session):
        sensor = _make_sensor(db_session)
        _make_rule(db_session)
        db_session.commit()

        matched = _engine_utc().get_matching_rules(sensor, db_session)
        assert len(matched) == 1

    def test_disabled_rule_not_matched(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session)
        rule.enabled = False
        db_session.commit()

        matched = _engine_utc().get_matching_rules(sensor, db_session)
        assert matched == []

    def test_wrong_trigger_type_not_matched(self, db_session):
        sensor = _make_sensor(db_session)
        _make_rule(db_session, trigger_type="cron")
        db_session.commit()

        matched = _engine_utc().get_matching_rules(sensor, db_session, trigger_type="sensor_event")
        assert matched == []

    def test_multiple_rules_all_matched(self, db_session):
        sensor = _make_sensor(db_session)
        _make_rule(db_session, name="Rule A")
        _make_rule(db_session, name="Rule B")
        db_session.commit()

        matched = _engine_utc().get_matching_rules(sensor, db_session)
        assert len(matched) == 2


class TestRulesEngineRateLimits:
    def test_cool_off_blocks_recent_completion(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session, cool_off_minutes=60)
        _log_completed(db_session, rule, minutes_ago=5)  # fired 5 min ago
        db_session.commit()

        matched = _engine_utc().get_matching_rules(sensor, db_session)
        assert matched == []

    def test_cool_off_allows_after_window(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session, cool_off_minutes=10)
        _log_completed(db_session, rule, minutes_ago=15)  # fired 15 min ago
        db_session.commit()

        matched = _engine_utc().get_matching_rules(sensor, db_session)
        assert len(matched) == 1

    def test_max_daily_triggers_blocks_at_limit(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session, max_daily_triggers=3)
        for _ in range(3):
            _log_completed(db_session, rule, minutes_ago=30)
        db_session.commit()

        matched = _engine_utc().get_matching_rules(sensor, db_session)
        assert matched == []

    def test_max_daily_triggers_allows_below_limit(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session, max_daily_triggers=5)
        for _ in range(3):
            _log_completed(db_session, rule, minutes_ago=30)
        db_session.commit()

        matched = _engine_utc().get_matching_rules(sensor, db_session)
        assert len(matched) == 1

    def test_zero_cool_off_never_blocks(self, db_session):
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session, cool_off_minutes=0)
        _log_completed(db_session, rule, minutes_ago=0)
        db_session.commit()

        matched = _engine_utc().get_matching_rules(sensor, db_session)
        assert len(matched) == 1


class TestRulesEngineDependencies:
    def test_require_success_passes_when_parent_completed(self, db_session):
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

        matched = _engine_utc().get_matching_rules(sensor, db_session)
        matched_names = {r.name for r in matched}
        assert "Child" in matched_names

    def test_require_success_fails_when_parent_not_completed(self, db_session):
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

        matched = _engine_utc().get_matching_rules(sensor, db_session)
        matched_names = {r.name for r in matched}
        assert "Child" not in matched_names


class TestRulesEngineContextFilters:
    def test_unknown_context_type_does_not_filter(self, db_session):
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

        matched = _engine_utc().get_matching_rules(sensor, db_session)
        assert len(matched) == 1

    def test_negated_unknown_context_still_allows_rule(self, db_session):
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

        matched = _engine_utc().get_matching_rules(sensor, db_session)
        # Unknown filter always passes (negate is ignored for unresolved types)
        assert len(matched) == 1
