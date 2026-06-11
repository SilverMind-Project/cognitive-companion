"""Unit tests for :class:`~backend.filters.builtin.dementia_signal.DementiaSignalFilter`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import backend.models  # noqa: F401
from backend.filters import FilterRegistry
from backend.filters.builtin.dementia_signal import DementiaSignalFilter
from backend.models.cts_signal import DementiaSignal

FilterRegistry.discover()

_NOW = datetime(2026, 4, 23, 20, 0, 0, tzinfo=UTC)

_SIGNAL_EVENT = {
    "kind": "dementia_signal",
    "payload": {
        "signal_id": 1,
        "signal_kind": "pacing",
        "person_id": "grandma",
        "severity": "warning",
        "window_start": "2026-04-23T19:30:00+00:00",
        "window_end": "2026-04-23T20:00:00+00:00",
        "evidence": {},
    },
}


@pytest.fixture
def filt() -> DementiaSignalFilter:
    instance = FilterRegistry.get("dementia_signal")
    assert instance is not None
    return instance  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestMetadata:
    def test_filter_type(self, filt: DementiaSignalFilter):
        assert filt.metadata().filter_type == "dementia_signal"

    def test_display_name(self, filt: DementiaSignalFilter):
        assert "Dementia" in filt.metadata().display_name


# ---------------------------------------------------------------------------
# Guard rails
# ---------------------------------------------------------------------------


class TestGuards:
    def test_non_dict_sensor_returns_false(self, filt: DementiaSignalFilter):
        assert filt.evaluate({}, "not-a-dict", _NOW) is False

    def test_wrong_kind_returns_false(self, filt: DementiaSignalFilter):
        event = {**_SIGNAL_EVENT, "kind": "sensor_event"}
        assert filt.evaluate({}, event, _NOW) is False

    def test_missing_payload_returns_false(self, filt: DementiaSignalFilter):
        assert filt.evaluate({}, {"kind": "dementia_signal"}, _NOW) is False


# ---------------------------------------------------------------------------
# Empty config matches any signal
# ---------------------------------------------------------------------------


class TestEmptyConfig:
    def test_empty_config_matches(self, filt: DementiaSignalFilter):
        assert filt.evaluate({}, _SIGNAL_EVENT, _NOW) is True


# ---------------------------------------------------------------------------
# kinds filter
# ---------------------------------------------------------------------------


class TestKindsFilter:
    def test_matching_kind_passes(self, filt: DementiaSignalFilter):
        assert filt.evaluate({"kinds": ["pacing"]}, _SIGNAL_EVENT, _NOW) is True

    def test_non_matching_kind_fails(self, filt: DementiaSignalFilter):
        assert filt.evaluate({"kinds": ["sundowning"]}, _SIGNAL_EVENT, _NOW) is False

    def test_multiple_kinds_matches_one(self, filt: DementiaSignalFilter):
        assert filt.evaluate({"kinds": ["sundowning", "pacing"]}, _SIGNAL_EVENT, _NOW) is True

    def test_fall_suspected_kind_matches(self, filt: DementiaSignalFilter):
        event = {
            "kind": "dementia_signal",
            "payload": {
                **_SIGNAL_EVENT["payload"],
                "signal_kind": "fall_suspected",
                "severity": "warning",
            },
        }
        assert filt.evaluate({"kinds": ["fall_suspected"]}, event, _NOW) is True

    def test_fall_suspected_does_not_match_other_kinds(self, filt: DementiaSignalFilter):
        event = {
            "kind": "dementia_signal",
            "payload": {
                **_SIGNAL_EVENT["payload"],
                "signal_kind": "fall_suspected",
                "severity": "warning",
            },
        }
        assert filt.evaluate({"kinds": ["pacing", "stillness_anomaly"]}, event, _NOW) is False

    def test_fall_suspected_matches_min_severity_warning(self, filt: DementiaSignalFilter):
        event = {
            "kind": "dementia_signal",
            "payload": {
                **_SIGNAL_EVENT["payload"],
                "signal_kind": "fall_suspected",
                "severity": "warning",
            },
        }
        assert filt.evaluate({"kinds": ["fall_suspected"], "min_severity": 0.66}, event, _NOW) is True

    def test_fall_suspected_fails_min_severity_emergency(self, filt: DementiaSignalFilter):
        event = {
            "kind": "dementia_signal",
            "payload": {
                **_SIGNAL_EVENT["payload"],
                "signal_kind": "fall_suspected",
                "severity": "warning",
            },
        }
        assert filt.evaluate({"kinds": ["fall_suspected"], "min_severity": 1.0}, event, _NOW) is False


# ---------------------------------------------------------------------------
# person_ids filter
# ---------------------------------------------------------------------------


class TestPersonIdsFilter:
    def test_matching_person_passes(self, filt: DementiaSignalFilter):
        assert filt.evaluate({"person_ids": ["grandma"]}, _SIGNAL_EVENT, _NOW) is True

    def test_non_matching_person_fails(self, filt: DementiaSignalFilter):
        assert filt.evaluate({"person_ids": ["dad"]}, _SIGNAL_EVENT, _NOW) is False


# ---------------------------------------------------------------------------
# min_severity filter
# ---------------------------------------------------------------------------


class TestMinSeverityFilter:
    def test_warning_passes_min_warning(self, filt: DementiaSignalFilter):
        assert filt.evaluate({"min_severity": 0.66}, _SIGNAL_EVENT, _NOW) is True

    def test_warning_fails_min_emergency(self, filt: DementiaSignalFilter):
        assert filt.evaluate({"min_severity": 1.0}, _SIGNAL_EVENT, _NOW) is False

    def test_info_fails_min_warning(self, filt: DementiaSignalFilter):
        event = {**_SIGNAL_EVENT, "payload": {**_SIGNAL_EVENT["payload"], "severity": "info"}}
        assert filt.evaluate({"min_severity": 0.66}, event, _NOW) is False


# ---------------------------------------------------------------------------
# time_of_day filter
# ---------------------------------------------------------------------------


class TestTimeOfDayFilter:
    def test_within_window_passes(self, filt: DementiaSignalFilter):
        cfg = {"time_of_day": {"start": "19:00", "end": "21:00"}}
        assert filt.evaluate(cfg, _SIGNAL_EVENT, _NOW) is True

    def test_outside_window_fails(self, filt: DementiaSignalFilter):
        cfg = {"time_of_day": {"start": "08:00", "end": "12:00"}}
        assert filt.evaluate(cfg, _SIGNAL_EVENT, _NOW) is False

    def test_midnight_crossing_window(self, filt: DementiaSignalFilter):
        # 20:00 UTC should match a 22:00-06:00 window
        cfg = {"time_of_day": {"start": "22:00", "end": "06:00"}}
        assert filt.evaluate(cfg, _SIGNAL_EVENT, _NOW) is False

        late_event = {
            **_SIGNAL_EVENT,
            "payload": {
                **_SIGNAL_EVENT["payload"],
                "window_end": "2026-04-23T23:00:00+00:00",
            },
        }
        assert filt.evaluate(cfg, late_event, _NOW) is True


# ---------------------------------------------------------------------------
# cooldown filter
# ---------------------------------------------------------------------------


class TestCooldownFilter:
    def test_no_cooldown_always_passes(self, filt: DementiaSignalFilter, db_session):
        assert filt.evaluate({"cooldown_minutes": 0}, _SIGNAL_EVENT, _NOW, db=db_session) is True

    def test_cooldown_passes_when_no_recent_ack(self, filt: DementiaSignalFilter, db_session):
        assert filt.evaluate({"cooldown_minutes": 30}, _SIGNAL_EVENT, _NOW, db=db_session) is True

    def test_cooldown_blocks_when_recent_ack_exists(self, filt: DementiaSignalFilter, db_session):
        # Insert a recently acknowledged signal.
        row = DementiaSignal(
            person_id="grandma",
            signal_type="pacing",
            severity="warning",
            window_start=_NOW - timedelta(minutes=60),
            window_end=_NOW - timedelta(minutes=30),
            value=5.0,
            acknowledged_at=_NOW - timedelta(minutes=10),
        )
        db_session.add(row)
        db_session.flush()

        result = filt.evaluate({"cooldown_minutes": 30}, _SIGNAL_EVENT, _NOW, db=db_session)
        assert result is False

    def test_cooldown_passes_when_ack_is_old(self, filt: DementiaSignalFilter, db_session):
        row = DementiaSignal(
            person_id="grandma",
            signal_type="pacing",
            severity="warning",
            window_start=_NOW - timedelta(hours=2),
            window_end=_NOW - timedelta(hours=1, minutes=30),
            value=5.0,
            acknowledged_at=_NOW - timedelta(hours=1),
        )
        db_session.add(row)
        db_session.flush()

        result = filt.evaluate({"cooldown_minutes": 30}, _SIGNAL_EVENT, _NOW, db=db_session)
        assert result is True
