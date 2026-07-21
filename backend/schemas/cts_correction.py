"""Segment-correction BFF envelopes.

The orchestrator owns the correction semantics: it proposes observation-
bounded segments, applies frame-only or bounded corrections (and explicit
Set-to-Unknown) under an optimistic version token, composes handoff splits, and
runs the asynchronous revision job. The BFF validates the upstream envelopes,
injects the audited actor from the auth context (never from the browser), and
returns these browser-facing models. The frontend derives no identity authority,
boundary, confidence, or job status.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Reason codes agreed; the browser may only send these.
ReasonCode = Literal[
    "wrong_person",
    "identity_uncertain",
    "track_handoff",
    "duplicate_hypothesis",
    "bad_bbox",
    "other",
]


# ---------------------------------------------------------------------------
# Proposal
# ---------------------------------------------------------------------------


class ProposeSegmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ph_id: str = Field(min_length=1, max_length=128)
    observation_id: str | None = Field(default=None, max_length=128)
    at: str | None = Field(default=None, max_length=64)


class SegmentBoundaryView(BaseModel):
    observation_id: str
    captured_at: str
    reason: str


class SegmentProposalResponse(BaseModel):
    ph_id: str
    observation_ids: list[str]
    start: SegmentBoundaryView
    end: SegmentBoundaryView
    ph_version: int
    effective_identity_id: str | None = None
    # CC internal key, mapped from effective_identity_id at this boundary.
    person_id: str | None = None


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


class ApplySegmentRequest(BaseModel):
    """Browser-facing apply payload. ``actor`` is NOT accepted here; the BFF
    injects the audited subject from the auth context."""

    model_config = ConfigDict(extra="forbid")

    ph_id: str = Field(min_length=1, max_length=128)
    reason_code: ReasonCode
    observation_start: str = Field(max_length=64)
    observation_end: str = Field(max_length=64)
    base_ph_version: int
    target_identity_id: str | None = Field(default=None, max_length=128)
    set_unknown: bool = False
    frame_only: bool = False
    note: str | None = Field(default=None, max_length=2048)
    source_view: str | None = Field(default=None, max_length=64)
    reviewed_frame_id: str | None = Field(default=None, max_length=128)
    reviewed_bbox: dict[str, Any] | None = None
    at_observation_id: str | None = Field(default=None, max_length=128)


class CorrectionResultResponse(BaseModel):
    revision_id: str
    correction_id: str
    ph_id: str
    previous_identity_id: str | None
    new_identity_id: str | None
    range_id: str
    new_ph_id: str | None
    job_status: str


# ---------------------------------------------------------------------------
# Job status (polled until terminal)
# ---------------------------------------------------------------------------


class CorrectionJobResponse(BaseModel):
    revision_id: str
    job_id: str
    status: str
    required_projections: list[str]
    row_counts: dict[str, int]
    attempts: int
    last_error: str | None = None
