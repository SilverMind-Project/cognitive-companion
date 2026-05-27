"""N2: Person Hypothesis response schemas (CC-enriched).

Every response model carries the enrichment fields the frontend needs:
identity_display_name, identity_color, room_name, presigned image URLs,
posterior_top_label and posterior_top_prob.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared enriched fields (mixed into every PH response)
# ---------------------------------------------------------------------------


class EnrichedFields(BaseModel):
    identity_display_name: str | None = None
    identity_color: str | None = None
    room_name: str | None = None
    latest_keyframe_image_url: str | None = None
    latest_keyframe_blurred_url: str | None = None
    posterior_top_label: str | None = None
    posterior_top_prob: float | None = None


# ---------------------------------------------------------------------------
# PH summary (list item)
# ---------------------------------------------------------------------------


class PHSummaryResponse(EnrichedFields):
    ph_id: str
    born_at: datetime | None = None
    last_seen_at: datetime | None = None
    closed_at: datetime | None = None
    observation_count: int = 0
    current_identity_id: str | None = None
    active_cameras: list[str] = Field(default_factory=list)
    last_floor_speed_m_s: float = 0.0
    last_posture: str | None = None


# ---------------------------------------------------------------------------
# PH detail
# ---------------------------------------------------------------------------


class PHDetailResponse(EnrichedFields):
    ph_id: str
    born_at: datetime | None = None
    last_seen_at: datetime | None = None
    closed_at: datetime | None = None
    observation_count: int = 0
    current_identity_id: str | None = None
    current_identity_committed_at: datetime | None = None
    active_cameras: list[str] = Field(default_factory=list)
    last_seen_camera: str = ""
    last_floor_speed_m_s: float = 0.0
    last_posture: str | None = None
    height_estimate_m: float | None = None
    state_mean: list[float] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------


class ObservationResponse(BaseModel):
    observation_id: str = ""
    camera_id: str = ""
    frame_index: int = 0
    captured_at: datetime | None = None
    floor_x_m: float = 0.0
    floor_y_m: float = 0.0
    detection_confidence: float = 0.0
    height_m: float | None = None


class PHObservationsResponse(BaseModel):
    ph_id: str
    items: list[ObservationResponse]
    count: int


# ---------------------------------------------------------------------------
# Trail point
# ---------------------------------------------------------------------------


class TrailPointResponse(BaseModel):
    camera_id: str = ""
    floor_x_m: float = 0.0
    floor_y_m: float = 0.0
    captured_at: datetime | None = None


# ---------------------------------------------------------------------------
# Revision
# ---------------------------------------------------------------------------


class RevisionResponse(BaseModel):
    revision_id: str
    ph_id: str
    previous_identity_id: str | None = None
    new_identity_id: str | None = None
    actor: str = ""
    reason: str = ""
    kind: str = ""
    applied_at: datetime | None = None
    rewritten_rows: int = 0


class RevisionsFeedResponse(BaseModel):
    items: list[RevisionResponse]
    has_more: bool


# ---------------------------------------------------------------------------
# Correction request / response bodies
# ---------------------------------------------------------------------------


class CorrectIdentityRequest(BaseModel):
    new_identity_id: str | None = Field(default=None, max_length=128)
    reason: str = Field(default="manual", max_length=512)


class MergeRequest(BaseModel):
    source_ph_id: str = Field(..., min_length=1, max_length=128)
    target_ph_id: str = Field(..., min_length=1, max_length=128)
    reason: str = Field(default="manual", max_length=512)


class SplitRequest(BaseModel):
    at_observation_id: str = Field(..., min_length=1, max_length=256)
    reason: str = Field(default="manual", max_length=512)


class BatchCorrectItem(BaseModel):
    ph_id: str = Field(..., min_length=1, max_length=128)
    new_identity_id: str | None = Field(default=None, max_length=128)
    reason: str = Field(default="manual", max_length=512)


class BatchCorrectRequest(BaseModel):
    corrections: list[BatchCorrectItem] = Field(..., min_length=1, max_length=50)


# ---------------------------------------------------------------------------
# Correction response bodies
# ---------------------------------------------------------------------------


class CorrectIdentityResponse(BaseModel):
    revision: RevisionResponse


class MergeResponse(BaseModel):
    revision: RevisionResponse
    source_ph_id: str
    target_ph_id: str


class SplitResponse(BaseModel):
    original_ph_id: str
    new_ph_id: str


class BatchCorrectResponse(BaseModel):
    revisions: list[RevisionResponse]
    applied: int
    errors: list[dict[str, str]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Paginated list
# ---------------------------------------------------------------------------


class PaginatedPHList(BaseModel):
    items: list[PHSummaryResponse]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Keyframes placeholder
# ---------------------------------------------------------------------------


class PHKeyframesResponse(BaseModel):
    ph_id: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0


# ---------------------------------------------------------------------------
# Trail
# ---------------------------------------------------------------------------


class PHTrailResponse(BaseModel):
    ph_id: str
    points: list[TrailPointResponse]
    count: int


# ---------------------------------------------------------------------------
# Co-present
# ---------------------------------------------------------------------------


class PHCoPresentResponse(BaseModel):
    ph_id: str
    co_present: list[str] = Field(default_factory=list)
    radius_m: float = 5.0


# ---------------------------------------------------------------------------
# WebSocket event payloads (N2 §3.3)
# Re-exported from cts_ph_ws for backward compatibility.
# ---------------------------------------------------------------------------

from backend.schemas.cts_ph_ws import PHCorrectionEvent, PHUpdateEvent  # noqa: E402, F401
