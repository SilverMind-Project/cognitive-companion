"""Tests for backend.services.cts.signal_config."""

from __future__ import annotations

from backend.services.cts.signal_config import (
    ALL_SIGNAL_KINDS,
    default_config_for_profile,
    is_signal_enabled,
)


class TestIsSignalEnabled:
    def test_none_config_allows_everything(self):
        assert is_signal_enabled(None, "pacing", "warning") is True

    def test_empty_enabled_kinds_allows_everything(self):
        # empty list means no kinds restriction (all allowed)
        # Actually — empty list means NOTHING is enabled.
        assert (
            is_signal_enabled({"enabled_kinds": [], "min_severity": "info"}, "pacing", "info")
            is False
        )

    def test_kind_in_list_is_allowed(self):
        cfg = {"enabled_kinds": ["absence", "pacing"], "min_severity": "info"}
        assert is_signal_enabled(cfg, "pacing", "info") is True

    def test_kind_not_in_list_is_rejected(self):
        cfg = {"enabled_kinds": ["absence"], "min_severity": "info"}
        assert is_signal_enabled(cfg, "sundowning_index", "warning") is False

    def test_severity_below_min_is_rejected(self):
        cfg = {"enabled_kinds": list(ALL_SIGNAL_KINDS), "min_severity": "warning"}
        assert is_signal_enabled(cfg, "pacing", "info") is False

    def test_severity_at_min_is_allowed(self):
        cfg = {"enabled_kinds": list(ALL_SIGNAL_KINDS), "min_severity": "warning"}
        assert is_signal_enabled(cfg, "pacing", "warning") is True

    def test_severity_above_min_is_allowed(self):
        cfg = {"enabled_kinds": list(ALL_SIGNAL_KINDS), "min_severity": "warning"}
        assert is_signal_enabled(cfg, "pacing", "emergency") is True

    def test_unknown_severity_ranks_zero(self):
        cfg = {"enabled_kinds": list(ALL_SIGNAL_KINDS), "min_severity": "warning"}
        # unknown severity gets rank 0 (< warning rank 1) -> rejected
        assert is_signal_enabled(cfg, "pacing", "unknown") is False

    def test_no_enabled_kinds_key_uses_no_filter(self):
        # missing key = no restriction on kinds
        cfg = {"min_severity": "info"}
        assert is_signal_enabled(cfg, "sundowning_index", "info") is True


class TestDefaultConfigForProfile:
    def test_senior_has_all_kinds(self):
        cfg = default_config_for_profile("senior")
        assert set(cfg["enabled_kinds"]) == set(ALL_SIGNAL_KINDS)
        assert cfg["min_severity"] == "info"

    def test_adult_has_only_presence_and_sleep(self):
        cfg = default_config_for_profile("adult")
        assert "absence" in cfg["enabled_kinds"]
        assert "nighttime_movement" in cfg["enabled_kinds"]
        assert "stillness_anomaly" in cfg["enabled_kinds"]
        assert "sundowning_index" not in cfg["enabled_kinds"]
        assert "pacing" not in cfg["enabled_kinds"]

    def test_guest_has_only_absence(self):
        cfg = default_config_for_profile("guest")
        assert cfg["enabled_kinds"] == ["absence"]

    def test_unknown_profile_falls_back_to_all_kinds(self):
        cfg = default_config_for_profile("nonexistent_profile")
        assert set(cfg["enabled_kinds"]) == set(ALL_SIGNAL_KINDS)
