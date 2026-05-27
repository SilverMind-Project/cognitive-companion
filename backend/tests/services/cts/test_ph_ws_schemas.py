"""Tests for PHUpdateEvent and PHCorrectionEvent WebSocket schemas."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.schemas.cts_ph_ws import PHCorrectionEvent, PHUpdateEvent


def test_ph_update_event_type_field_default():
    evt = PHUpdateEvent(ph_id="ph-123")
    assert evt.type == "cts_ph_update"


def test_ph_update_event_model_dump_mode_json_serializes_datetime():
    evt = PHUpdateEvent(
        ph_id="ph-abc",
        current_identity_id="alice",
        last_observed_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    d = evt.model_dump(mode="json")
    assert d["type"] == "cts_ph_update"
    assert d["ph_id"] == "ph-abc"
    assert d["current_identity_id"] == "alice"
    assert isinstance(d["last_observed_at"], str)
    assert "2026" in d["last_observed_at"]


def test_ph_correction_event_type_field_default():
    evt = PHCorrectionEvent(revision_id="rev-1", ph_id="ph-1")
    assert evt.type == "cts_ph_correction"


def test_ph_update_event_wire_field_names_stable():
    """Field names must match what frontend usePHList.handleWsEvent() reads."""
    evt = PHUpdateEvent(ph_id="x")
    d = evt.model_dump()
    assert "type" in d
    assert "current_identity_id" in d
    assert "last_observed_at" in d
