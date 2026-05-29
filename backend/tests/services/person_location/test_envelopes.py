"""U2-T3: PersonLocationEnvelope always carries all quality fields (D5/rule 15)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.schemas.cts_envelopes import (
    PersonLocationEnvelope,
    RoomOccupancyEnvelope,
    envelope_to_mcp,
    occupancy_to_mcp,
)
from backend.services.person_location.types import CurrentLocation


def _make_loc(
    *,
    quality: float = 0.7,
    confidence: float = 0.9,
    last_observed_at: datetime | None = None,
) -> CurrentLocation:
    return CurrentLocation(
        person_id="alice",
        room_id=1,
        room_name="bedroom",
        since=datetime(2026, 5, 29, 10, 0, 0, tzinfo=UTC),
        entry_source="observed",
        confidence=confidence,
        is_inferred=False,
        quality=quality,
        last_observed_at=last_observed_at,
    )


# ---------------------------------------------------------------------------
# PersonLocationEnvelope construction
# ---------------------------------------------------------------------------


def test_envelope_from_current_location_carries_all_quality_fields():
    now = datetime(2026, 5, 29, 10, 5, 0, tzinfo=UTC)
    last_obs = datetime(2026, 5, 29, 10, 4, 0, tzinfo=UTC)
    loc = _make_loc(quality=0.75, confidence=0.85, last_observed_at=last_obs)

    env = PersonLocationEnvelope.from_current_location(loc, display_name="Grandma", now=now)

    assert env.quality == pytest.approx(0.75)
    assert env.confidence == pytest.approx(0.85)
    assert env.staleness_seconds == 60
    assert env.source == "observation"
    assert env.display_name == "Grandma"


def test_envelope_source_inferred_transit():
    loc = CurrentLocation(
        person_id="bob",
        room_id=2,
        room_name="hallway",
        since=datetime(2026, 5, 29, 9, 0, 0, tzinfo=UTC),
        entry_source="inferred_transit",
        confidence=0.5,
        is_inferred=True,
        quality=0.3,
    )
    env = PersonLocationEnvelope.from_current_location(loc, display_name="Bob")
    assert env.source == "transition"
    assert env.is_inferred is True


def test_envelope_source_manual():
    loc = CurrentLocation(
        person_id="carol",
        room_id=3,
        room_name="kitchen",
        since=datetime(2026, 5, 29, 8, 0, 0, tzinfo=UTC),
        entry_source="manual",
        confidence=1.0,
        is_inferred=False,
        quality=1.0,
    )
    env = PersonLocationEnvelope.from_current_location(loc, display_name="Carol")
    assert env.source == "manual_override"


def test_envelope_staleness_no_last_observed():
    loc = _make_loc(last_observed_at=None)
    env = PersonLocationEnvelope.from_current_location(loc, display_name="")
    assert env.staleness_seconds == 0


def test_envelope_requires_quality_field():
    """Constructing without quality raises (D5: quality is always present)."""
    with pytest.raises(ValidationError):
        PersonLocationEnvelope(
            person_id="alice",
            room_id=1,
            room_name="bedroom",
            since=datetime(2026, 5, 29, 10, 0, 0, tzinfo=UTC),
            entry_source="observed",
            confidence=0.9,
            is_inferred=False,
            display_name="Alice",
            # quality omitted
            staleness_seconds=0,
            source="observation",
        )


def test_envelope_requires_staleness_seconds():
    with pytest.raises(ValidationError):
        PersonLocationEnvelope(
            person_id="alice",
            room_id=1,
            room_name="bedroom",
            since=datetime(2026, 5, 29, 10, 0, 0, tzinfo=UTC),
            entry_source="observed",
            confidence=0.9,
            is_inferred=False,
            display_name="Alice",
            quality=0.5,
            # staleness_seconds omitted
            source="observation",
        )


def test_envelope_requires_source():
    with pytest.raises(ValidationError):
        PersonLocationEnvelope(
            person_id="alice",
            room_id=1,
            room_name="bedroom",
            since=datetime(2026, 5, 29, 10, 0, 0, tzinfo=UTC),
            entry_source="observed",
            confidence=0.9,
            is_inferred=False,
            display_name="Alice",
            quality=0.5,
            staleness_seconds=0,
            # source omitted
        )


def test_envelope_confidence_bounds():
    """Confidence outside [0,1] raises."""
    with pytest.raises(ValidationError):
        PersonLocationEnvelope(
            person_id="x",
            room_id=1,
            room_name="r",
            since=datetime(2026, 5, 29, tzinfo=UTC),
            entry_source="observed",
            confidence=1.5,  # out of range
            is_inferred=False,
            display_name="",
            quality=0.5,
            staleness_seconds=0,
            source="observation",
        )


# ---------------------------------------------------------------------------
# Pre-U2 field preservation (D7)
# ---------------------------------------------------------------------------


def test_envelope_contains_all_pre_u2_fields():
    """PersonLocationEnvelope is a strict superset of pre-U2 CurrentLocationOut."""
    pre_u2_fields = {
        "person_id",
        "room_id",
        "room_name",
        "since",
        "entry_source",
        "confidence",
        "is_inferred",
    }
    env = PersonLocationEnvelope.from_current_location(_make_loc(), display_name="")
    env_dict = env.model_dump()
    missing = pre_u2_fields - set(env_dict.keys())
    assert not missing, f"Envelope missing pre-U2 fields: {missing}"


# ---------------------------------------------------------------------------
# RoomOccupancyEnvelope
# ---------------------------------------------------------------------------


def test_room_occupancy_envelope_contains_pre_u2_fields():
    """RoomOccupancyEnvelope is a strict superset of pre-U2 OccupantsResponse."""
    pre_u2_fields = {"room_id", "as_of", "occupants"}
    now = datetime.now(UTC)
    env = RoomOccupancyEnvelope(
        room_id=1,
        room_name="bedroom",
        occupants=[],
        as_of=now,
    )
    env_dict = env.model_dump()
    missing = pre_u2_fields - set(env_dict.keys())
    assert not missing, f"RoomOccupancyEnvelope missing pre-U2 fields: {missing}"


# ---------------------------------------------------------------------------
# MCP adapters
# ---------------------------------------------------------------------------


def test_envelope_to_mcp_flattens_floor_point():
    loc = _make_loc()
    env = PersonLocationEnvelope.from_current_location(loc, display_name="Alice")
    d = envelope_to_mcp(env)
    assert "floor_point" not in d
    # No floor point set, so x/y keys not present.
    assert "floor_x_m" not in d


def test_occupancy_to_mcp_returns_occupants_list():
    now = datetime.now(UTC)
    loc = _make_loc()
    env = RoomOccupancyEnvelope(
        room_id=1,
        room_name="bedroom",
        occupants=[PersonLocationEnvelope.from_current_location(loc, display_name="", now=now)],
        as_of=now,
    )
    d = occupancy_to_mcp(env)
    assert d["room_id"] == 1
    assert d["room_name"] == "bedroom"
    assert isinstance(d["occupants"], list)
    assert len(d["occupants"]) == 1
