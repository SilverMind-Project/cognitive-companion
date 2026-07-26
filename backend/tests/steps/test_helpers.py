"""Unit tests for :mod:`backend.steps._helpers`."""

from __future__ import annotations

from backend.steps._helpers import resolve_person_id


class TestResolvePersonId:
    def test_explicit_config_person_id_wins(self):
        assert resolve_person_id({"person_id": "alice"}, {"person_id": "bob"}) == "alice"

    def test_falls_back_to_persons_list(self):
        assert resolve_person_id({}, {"persons": [{"person_id": "alice"}]}) == "alice"

    def test_falls_back_to_persons_list_id_key(self):
        assert resolve_person_id({}, {"persons": [{"id": "alice"}]}) == "alice"

    def test_falls_back_to_scalar_person_id(self):
        assert resolve_person_id({}, {"person_id": "alice"}) == "alice"

    def test_falls_back_to_trigger_event_person_id(self):
        """A dementia_signal-fired pipeline carries person_id only under
        pipeline_data['trigger_event'], not the top-level scalar or persons list."""
        pipeline_data = {"trigger_event": {"person_id": "alice", "signal_kind": "x"}}
        assert resolve_person_id({}, pipeline_data) == "alice"

    def test_config_wins_over_trigger_event(self):
        pipeline_data = {"trigger_event": {"person_id": "alice"}}
        assert resolve_person_id({"person_id": "bob"}, pipeline_data) == "bob"

    def test_nothing_resolvable_returns_none(self):
        assert resolve_person_id({}, {}) is None

    def test_trigger_event_without_person_id_returns_none(self):
        assert resolve_person_id({}, {"trigger_event": {"signal_kind": "x"}}) is None
