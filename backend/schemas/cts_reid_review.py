"""ReID review-queue BFF envelopes.

The orchestrator owns the governed gallery lifecycle and computes
per-candidate eligibility. The BFF validates the upstream envelopes, injects the
audited actor from the auth context (never the browser), maps the effective
identity onto Cognitive Companion's ``person_id``, and presigns crop/full-frame
media only when the object still exists (rejected rows have no live crop). The
frontend derives no eligibility, identity authority, or lifecycle state.

Reason codes mirror the correction vocabulary so reviewers see one
consistent set across the keyframe, PH, and gallery surfaces.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RejectReasonCode = Literal[
    "wrong_person",
    "identity_uncertain",
    "low_quality",
    "duplicate_candidate",
    "bad_bbox",
    "other",
]

# The fourth gallery lifecycle state, auto_verified,
# sits between pending_review and operator_verified. A candidate can also be
# terminally rejected. Only these four values are ever valid on the wire; an
# out-of-vocabulary state from a stale or newer upstream is a contract violation
# (502), not silently accepted.
ReviewState = Literal["pending_review", "auto_verified", "operator_verified", "rejected"]


# ---------------------------------------------------------------------------
# Candidate views
# ---------------------------------------------------------------------------


class EligibilityView(BaseModel):
    eligible: bool
    model_compatible: bool
    reasons: list[str]


class ReviewCandidateView(BaseModel):
    candidate_id: str
    # Proposed/effective identity plus the CC-internal person_id mapped at this
    # boundary from effective_identity_id.
    identity_id: str | None = None
    proposed_identity_id: str | None = None
    effective_identity_id: str | None = None
    person_id: str | None = None
    state: ReviewState
    label_source: str | None = None
    candidate_reason: str | None = None
    model_version: str | None = None
    preprocessing_version: str | None = None
    dimension: int | None = None
    bbox: dict[str, Any] | None = None
    crop_width: int | None = None
    crop_height: int | None = None
    ph_id: str | None = None
    observation_id: str | None = None
    keyframe_id: str | None = None
    camera_id: str | None = None
    capture_time: str | None = None
    confidence: float | None = None
    orientation: int
    quality: float
    is_truncated: bool
    is_occluded: bool
    source_episode_id: str | None = None
    created_actor: str | None = None
    created_at: str | None = None
    seen_at: str | None = None
    reviewed_actor: str | None = None
    reviewed_time: str | None = None
    review_reason: str | None = None
    review_note: str | None = None
    audit_version: int
    # Presigned media; null when the object is unavailable (e.g. rejected crop).
    crop_url: str | None = None
    frame_url: str | None = None


class ReviewCandidateListResponse(BaseModel):
    candidates: list[ReviewCandidateView]
    total: int
    limit: int
    offset: int


class ReviewEventView(BaseModel):
    event_id: str
    entry_id: str
    previous_state: str
    new_state: str
    actor: str
    reason: str | None = None
    note: str | None = None
    event_time: str
    audit_version: int


class ReviewCandidateDetailResponse(BaseModel):
    candidate: ReviewCandidateView
    events: list[ReviewEventView]
    eligibility: EligibilityView


class ReviewEventsResponse(BaseModel):
    events: list[ReviewEventView]


class ReviewCountsResponse(BaseModel):
    pending_review: int
    auto_verified: int
    operator_verified: int
    rejected: int


# ---------------------------------------------------------------------------
# Action requests (actor injected server-side; never accepted from the browser)
# ---------------------------------------------------------------------------


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_audit_version: int
    note: str | None = Field(default=None, max_length=2048)


class RelabelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_audit_version: int
    target_identity_id: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=2048)


class DemoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_audit_version: int
    note: str | None = Field(default=None, max_length=2048)


class RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_audit_version: int
    reason: RejectReasonCode
    note: str | None = Field(default=None, max_length=2048)


class BatchRejectItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=128)
    base_audit_version: int


class BatchRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: RejectReasonCode
    note: str | None = Field(default=None, max_length=2048)
    items: list[BatchRejectItemRequest] = Field(min_length=1, max_length=200)


class BatchRejectResultItem(BaseModel):
    candidate_id: str
    ok: bool
    error_code: str | None = None
    error_message: str | None = None


class BatchRejectResponse(BaseModel):
    results: list[BatchRejectResultItem]
    rejected: int
    failed: int
