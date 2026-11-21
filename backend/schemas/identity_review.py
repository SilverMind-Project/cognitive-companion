"""Shared contracts for every place an operator says who a face, body, or track belongs to.

Identity is reviewed on several surfaces, each owned by a different service: face calibration
captures and visitor clusters (person-identification-service), body-appearance samples and track
corrections (tracking orchestrator). Each owner keeps its own rules. What they share is defined
here once: who can be chosen (``IdentityTargetsEnvelope``), what an operator can say
(``ReviewVerdict``), and the shape of a batch decision's outcome (``BatchReviewResponse``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# What an operator can say about a subject. Each surface accepts the verdicts that make sense for
# it and maps them to its owner's action:
#   is_member     "This is X" (needs target_identity_id)
#   new_person    "Someone new; add them to the household"
#   not_enrolled  "Someone who is not in the household"
#   not_usable    "Not a usable face or body"
ReviewVerdict = Literal["is_member", "new_person", "not_enrolled", "not_usable"]

# The review surfaces that speak the shared verdicts. Track corrections (keyframes, the PH
# inspector, the live view) keep their own correction workflow and are not listed here.
ReviewSurface = Literal["visitors", "face_calibration", "reid_review"]

ReviewErrorCode = Literal[
    "not_found",
    "already_named",
    "unknown_member",
    "not_enrolled_member",
    # The subject changed since it was loaded (a stale version) or is no longer eligible.
    "conflict",
    "upstream_error",
]


class ReviewVerdictOut(BaseModel):
    verdict: ReviewVerdict
    effect: str = Field(
        description=(
            "What the decision changes, in plain words; may name the chosen member with the "
            "envelope's member_placeholder"
        )
    )
    needs_target: bool = Field(description="The decision names a household member")
    needs_enrolled_face: bool = Field(
        description="The named member must have enrolled faces in person identification"
    )
    batch: bool = Field(description="The surface accepts this decision for several subjects")


class ReviewSurfaceOut(BaseModel):
    surface: ReviewSurface
    guarantee: str = Field(description="Which decisions on this surface can change enrollment")
    verdicts: list[ReviewVerdictOut] = Field(description="The verdicts this surface accepts")


class ReviewVocabularyEnvelope(BaseModel):
    surfaces: list[ReviewSurfaceOut]
    member_placeholder: str = Field(description="Replaced by the chosen member's display name")
    wearable_revocation_effect: str = Field(
        default="",
        description="What revoking a wearable association's teaching changes, in plain words",
    )


class IdentityTargetOut(BaseModel):
    identity_id: str
    display_name: str
    is_active: bool
    is_guest: bool
    face_enrolled: bool | None = Field(
        description=(
            "Has enrolled face photos in person identification; null when that service could "
            "not be read. Decisions that need an enrolled face disable the others."
        )
    )
    gallery_entry_count: int | None = Field(
        default=None, description="ReID gallery rows; decoration only, null when unavailable"
    )
    gallery_verified_count: int | None = None


class IdentityTargetsEnvelope(BaseModel):
    targets: list[IdentityTargetOut] = Field(description="Active household members, by name")
    enrollment_available: bool = Field(
        description="False when person identification could not be read"
    )
    gallery_available: bool = Field(description="False when the tracking orchestrator failed")


class ReviewItemResult(BaseModel):
    id: str
    ok: bool
    error_code: ReviewErrorCode | None = None


class BatchReviewResponse(BaseModel):
    results: list[ReviewItemResult] = Field(description="One result per subject, in order")
    reviewed: int = Field(ge=0)
    failed: int = Field(ge=0)
    effect: str = Field(description="What the decision changed, in one plain sentence")


class VisitorReviewRequest(BaseModel):
    """Decide about several visitor clusters at once."""

    model_config = {"extra": "forbid"}

    cluster_ids: list[str] = Field(..., min_length=1, max_length=200)
    verdict: Literal["is_member", "not_enrolled", "not_usable"]
    target_identity_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Required for is_member: an active household member with enrolled faces",
    )
