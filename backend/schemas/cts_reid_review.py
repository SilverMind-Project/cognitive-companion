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

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


# "Not usable" says which kind; "not in the household" is always wrong_person.
UnusableReasonCode = Literal[
    "identity_uncertain", "low_quality", "duplicate_candidate", "bad_bbox", "other"
]


class ReIDReviewBatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=128)
    base_audit_version: int


class ReIDReviewBatchRequest(BaseModel):
    """Decide about several body samples at once: only rejections, never approval.

    ``not_enrolled`` rejects as ``wrong_person``; ``not_usable`` needs the unusable ``reason``.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["not_enrolled", "not_usable"]
    reason: UnusableReasonCode | None = None
    note: str | None = Field(default=None, max_length=2048)
    items: list[ReIDReviewBatchItem] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _reason_only_when_unusable(self) -> ReIDReviewBatchRequest:
        if (self.verdict == "not_usable") != (self.reason is not None):
            raise ValueError("reason is required for not_usable and only for it")
        return self
