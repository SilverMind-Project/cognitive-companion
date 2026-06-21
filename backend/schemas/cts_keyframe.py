"""M07 grouped keyframe envelopes.

The BFF validates the orchestrator's physical-frame read model with the
``Upstream*`` models (a contract violation surfaces as a typed 502, never an
empty UI) and returns the browser-facing ``PhysicalFrameCard`` page.

Identity is server-owned: the orchestrator supplies per-bbox inferred/effective
identity, authority, decision source, calibrated confidence, conflict, and
pending-review state. The BFF only composes the card summary (group by
effective identity, count, collect source badges) and maps the effective
identity onto Cognitive Companion's internal ``person_id`` at this boundary.
The frontend derives none of these.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Upstream contract (validated; missing/typed-wrong fields -> 502)
# ---------------------------------------------------------------------------


class UpstreamBbox(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ph_id: str
    x1: float
    y1: float
    x2: float
    y2: float
    detection_confidence: float
    frame_width: int
    frame_height: int
    inferred_identity_id: str | None = None
    effective_identity_id: str | None = None
    authority: str
    decision_source: str
    calibrated_confidence: float | None = None
    conflict: bool
    conflict_kind: str | None = None
    revision_id: str | None = None
    pending_review: bool
    bbox_id: str | None = None
    override_x1: float | None = None
    override_y1: float | None = None
    override_x2: float | None = None
    override_y2: float | None = None


class UpstreamTrigger(BaseModel):
    model_config = ConfigDict(extra="ignore")

    keyframe_id: str
    ph_id: str
    tag_reason: str


class UpstreamFrame(BaseModel):
    model_config = ConfigDict(extra="ignore")

    physical_frame_id: str
    camera_id: str
    minio_key: str
    captured_at: str
    frame_width: int
    frame_height: int
    triggers: list[UpstreamTrigger]
    trigger_reasons: list[str]
    unknown_count: int
    conflict_count: int
    pending_review_count: int
    bboxes: list[UpstreamBbox]


class UpstreamKeyframePage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    frames: list[UpstreamFrame]
    total: int
    truncated: bool = False


# ---------------------------------------------------------------------------
# Browser-facing envelope
# ---------------------------------------------------------------------------


class KeyframeBboxView(BaseModel):
    """One bbox with full effective-identity provenance for overlays."""

    bbox_id: str | None
    ph_id: str
    x1: float
    y1: float
    x2: float
    y2: float
    detection_confidence: float
    frame_width: int
    frame_height: int
    inferred_identity_id: str | None
    effective_identity_id: str | None
    # CC internal key, mapped from effective_identity_id at this boundary.
    person_id: str | None
    authority: str
    decision_source: str
    calibrated_confidence: float | None
    conflict: bool
    conflict_kind: str | None
    revision_id: str | None
    pending_review: bool
    override_x1: float | None = None
    override_y1: float | None = None
    override_x2: float | None = None
    override_y2: float | None = None


class IdentitySummaryItem(BaseModel):
    """One row of the card summary: an effective identity and its bbox count."""

    effective_identity_id: str | None
    person_id: str | None
    count: int
    source_badges: list[str]


class KeyframeTriggerView(BaseModel):
    keyframe_id: str
    ph_id: str
    tag_reason: str


class PhysicalFrameCard(BaseModel):
    """One card per physical source frame."""

    physical_frame_id: str
    camera_id: str
    minio_key: str
    captured_at: str
    frame_width: int
    frame_height: int
    image_url: str | None = None
    triggers: list[KeyframeTriggerView]
    trigger_reasons: list[str]
    identity_summary: list[IdentitySummaryItem]
    unknown_count: int
    conflict_count: int
    pending_review_count: int
    bboxes: list[KeyframeBboxView]
    # Back-compat fields some existing consumers/tests still read.
    keyframe_id: str = ""
    sample_id: str = ""


class KeyframePage(BaseModel):
    keyframes: list[PhysicalFrameCard]
    count: int
    total: int
    # True when the upstream scan hit its window cap, so total counts only the
    # most recent window rather than all history.
    truncated: bool = False
    limit: int = Field(default=50)
    offset: int = Field(default=0)
