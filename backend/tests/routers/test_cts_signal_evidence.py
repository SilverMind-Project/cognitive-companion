"""WTR8: Signal evidence endpoint tests."""

from __future__ import annotations

from backend.routers.cts_signal_evidence import SignalEvidenceResponse, SignalEvidenceSegment


def test_evidence_response_includes_segments_field():
    """SignalEvidenceResponse must separate observed_segments and inferred_segments."""
    model = SignalEvidenceResponse(
        signal={"id": 1, "signal_type": "bathroom_dwell_anomaly"},
        window={"start": "2026-01-01T00:00:00Z", "end": "2026-01-01T01:00:00Z"},
        observed_segments=[
            SignalEvidenceSegment(
                segment_id="seg-1",
                room_id=1,
                room_name="Bathroom",
                entered_at="2026-01-01T00:00:00Z",
                dwell_seconds=120.0,
                entry_source="observed",
                is_inferred=False,
            )
        ],
        inferred_segments=[
            SignalEvidenceSegment(
                segment_id="seg-2",
                room_id=2,
                room_name="Bedroom",
                entered_at="2026-01-01T00:10:00Z",
                dwell_seconds=60.0,
                entry_source="inferred_transit",
                is_inferred=True,
            )
        ],
        narrative="Test narrative",
        algorithm_version="1.2.0",
        threshold_metadata={"threshold_minutes": 30, "value": 45.0},
    )
    data = model.model_dump(mode="json")
    assert len(data["observed_segments"]) == 1
    assert len(data["inferred_segments"]) == 1
    assert data["inferred_segments"][0]["is_inferred"] is True
    assert data["observed_segments"][0]["is_inferred"] is False
    assert data["algorithm_version"] == "1.2.0"
    assert data["threshold_metadata"]["threshold_minutes"] == 30


def test_inferred_segment_labeled_in_response():
    """Inferred segments must have is_inferred=True."""
    seg = SignalEvidenceSegment(
        segment_id="seg-3",
        room_id=3,
        room_name="Bathroom",
        dwell_seconds=300.0,
        entry_source="inferred_transit",
        is_inferred=True,
    )
    assert seg.is_inferred is True
    assert seg.entry_source == "inferred_transit"


def test_evidence_response_algorithm_version_present():
    """Every signal evidence must include algorithm_version."""
    resp = SignalEvidenceResponse(
        signal={"algorithm_version": "2.1.0"},
        algorithm_version="2.1.0",
    )
    assert resp.algorithm_version == "2.1.0"
