"""Unified BFF response envelopes for CTS concepts.

Every data-quality field (confidence, quality, staleness_seconds, source) is
always present and always server-computed. The frontend renders them; it never
invents them (design rule D5). The envelope is a strict superset of prior
CurrentLocationOut keys so existing consumers keep working (design rule D7).

MCP tools use envelope_to_mcp() to adapt these to dict form without duplicating
the field mapping.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.services.person_location.types import CurrentLocation

# ---------------------------------------------------------------------------
# Source enum mapping (entry_source → canonical source)
# entry_source is kept verbatim in the envelope for D7 back-compat;
# source is the new canonical provenance badge.
# ---------------------------------------------------------------------------

EnvelopeSource = Literal[
    "observation",
    "transition",
    "manual_override",
    "ph_continuation",
]

_ENTRY_SOURCE_TO_ENVELOPE: dict[str, EnvelopeSource] = {
    "observed": "observation",
    "inferred_transit": "transition",
    "manual": "manual_override",
}


def _map_source(entry_source: str, is_inferred: bool) -> EnvelopeSource:
    """Map legacy entry_source + is_inferred to canonical EnvelopeSource."""
    if entry_source in _ENTRY_SOURCE_TO_ENVELOPE:
        return _ENTRY_SOURCE_TO_ENVELOPE[entry_source]
    if is_inferred:
        return "transition"
    return "observation"


def _staleness_seconds(last_observed_at: datetime | None, now: datetime) -> int:
    if last_observed_at is None:
        return 0
    diff = (now - last_observed_at).total_seconds()
    return max(0, int(diff))


# ---------------------------------------------------------------------------
# PersonLocationEnvelope
# ---------------------------------------------------------------------------


class FloorPointEnvelope(BaseModel):
    """Floor-plan coordinate in metres."""

    x_m: float
    y_m: float


class PersonLocationEnvelope(BaseModel):
    """Current location for one person.

    superset of prior CurrentLocationOut fields, all present
    (person_id, room_id, room_name, since, entry_source, confidence,
    is_inferred) plus data-quality fields.
    """

    # --- Legacy CurrentLocationOut fields (kept verbatim) ---
    person_id: str
    room_id: int
    room_name: str
    since: datetime = Field(description="ISO-8601 UTC timestamp when this segment opened.")
    entry_source: str = Field(description="Raw entry source from the segment state machine.")
    confidence: float = Field(ge=0.0, le=1.0)
    is_inferred: bool

    # --- Data-quality fields ---
    display_name: str = Field(description="Human-readable name from HouseholdMember.")
    quality: float = Field(ge=0.0, le=1.0, description="PH mean_quality from CTS wire.")
    staleness_seconds: int = Field(ge=0, description="Seconds since last observation.")
    source: EnvelopeSource = Field(description="Canonical provenance badge for UI display.")
    floor_point: FloorPointEnvelope | None = Field(
        default=None, description="Last known floor position in metres."
    )

    @classmethod
    def from_current_location(
        cls,
        loc: CurrentLocation,
        *,
        display_name: str = "",
        now: datetime | None = None,
    ) -> PersonLocationEnvelope:
        _now = now or datetime.now(UTC)
        return cls(
            person_id=loc.person_id,
            room_id=loc.room_id,
            room_name=loc.room_name,
            since=loc.since,
            entry_source=loc.entry_source,
            confidence=loc.confidence,
            is_inferred=loc.is_inferred,
            display_name=display_name,
            quality=loc.quality,
            staleness_seconds=_staleness_seconds(loc.last_observed_at, _now),
            source=_map_source(loc.entry_source, loc.is_inferred),
            floor_point=None,
        )


# ---------------------------------------------------------------------------
# RoomOccupancyEnvelope
# ---------------------------------------------------------------------------


class RoomOccupancyEnvelope(BaseModel):
    """Current occupancy of one room."""

    room_id: int
    room_name: str
    occupants: list[PersonLocationEnvelope]
    as_of: datetime = Field(description="ISO-8601 UTC timestamp of this snapshot.")


# ---------------------------------------------------------------------------
# DementiaSignalEnvelope
# ---------------------------------------------------------------------------


class DementiaSignalEnvelope(BaseModel):
    """One dementia signal with quality metadata for the UI.

    superset of prior signal_store._to_dict() fields, all present
    (id, signal_id, person_id, signal_type, severity, window_start, window_end,
    value, baseline, z_score, context_json, algorithm_version, acknowledged_at,
    received_at) plus data-quality fields.
    """

    # --- Legacy signal_store._to_dict() fields (kept verbatim) ---
    id: int | None = None
    signal_id: str | None = None
    person_id: str | None = None
    signal_type: str
    severity: str
    window_start: str | None = None
    window_end: str | None = None
    value: float | None = None
    baseline: float | None = None
    z_score: float | None = None
    context_json: dict[str, Any] | None = None
    algorithm_version: int | None = None
    acknowledged_at: str | None = None
    feedback: str | None = None
    evidence_grade: str | None = None
    received_at: str | None = None

    # --- Data-quality fields ---
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_ref: str | None = Field(default=None, description="Link to supporting evidence.")
    narrative: str = Field(
        default="", description="Human-readable plain-language summary of this signal."
    )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DementiaSignalEnvelope:
        from backend.services.cts.signal_narratives import narrative_for

        signal_type = str(d.get("signal_type", ""))
        # Use safe defaults; rich context params are optional and UI-only.
        try:
            narrative = narrative_for(kind=signal_type)
        except Exception:  # noqa: BLE001
            narrative = signal_type.replace("_", " ").capitalize()
        return cls(
            id=d.get("id"),
            signal_id=d.get("signal_id"),
            person_id=d.get("person_id"),
            signal_type=signal_type,
            severity=str(d.get("severity", "info")),
            window_start=d.get("window_start"),
            window_end=d.get("window_end"),
            value=d.get("value"),
            baseline=d.get("baseline"),
            z_score=d.get("z_score"),
            context_json=d.get("context_json"),
            algorithm_version=d.get("algorithm_version"),
            acknowledged_at=d.get("acknowledged_at"),
            feedback=d.get("feedback"),
            evidence_grade=d.get("evidence_grade"),
            received_at=d.get("received_at"),
            confidence=1.0,
            evidence_ref=None,
            narrative=narrative,
        )


# ---------------------------------------------------------------------------
# TrackedPersonSummaryEnvelope
# ---------------------------------------------------------------------------


class TrackedPersonSummaryEnvelope(BaseModel):
    """Summary of one tracked household member."""

    person_id: str
    display_name: str
    current_location: PersonLocationEnvelope | None = None
    last_seen: datetime | None = Field(
        default=None, description="ISO-8601 UTC timestamp of last sighting."
    )
    open_signal_count: int = Field(default=0, ge=0)
    mean_quality: float = Field(default=0.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# MCP adapter
# ---------------------------------------------------------------------------


def envelope_to_mcp(envelope: PersonLocationEnvelope) -> dict[str, Any]:
    """Convert a PersonLocationEnvelope to a flat dict for MCP tool return.

    MCP tools return plain dicts; this adapter keeps the MCP shape in sync
    with the envelope without duplicating field mappings (design rule D6).
    """
    d = envelope.model_dump()
    # Flatten floor_point for ergonomic MCP use.
    if d.get("floor_point"):
        d["floor_x_m"] = d["floor_point"]["x_m"]
        d["floor_y_m"] = d["floor_point"]["y_m"]
    del d["floor_point"]
    return d


def occupancy_to_mcp(envelope: RoomOccupancyEnvelope) -> dict[str, Any]:
    """Convert a RoomOccupancyEnvelope to a dict for MCP tool return."""
    return {
        "room_id": envelope.room_id,
        "room_name": envelope.room_name,
        "as_of": envelope.as_of.isoformat(),
        "occupants": [envelope_to_mcp(o) for o in envelope.occupants],
    }
