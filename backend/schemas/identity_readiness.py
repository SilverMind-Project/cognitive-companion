"""Identity readiness envelope: which link of the identity chain is broken, and what to do next.

Identity setup is a chain that crosses three services: enroll everyone (People), capture face
crops (person-identification-service), label them (Face calibration), fit and deploy the
calibration artifact, run calibrated face evidence in CTS (shadow, then live), and let calibrated
faces propose body-appearance samples for the ReID Review Queue. Camera ingest and the floor frame
are prerequisites beside the chain. Each step reports one state and one next action; the frontend
maps the action to copy and a link.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.identity_review import ReviewSurface

ReadinessStepKey = Literal[
    "roster",
    "ingest",
    "floor_frame",
    "capture",
    "labeling",
    "artifact",
    "face_policy",
    "templates",
    "body_gallery",
    "wearables",
    "wearable_learners",
]

# unknown: the step's source failed. The page never guesses a state it could not read.
ReadinessState = Literal["ready", "attention", "blocked", "unknown"]

ReadinessNextAction = Literal[
    "none",
    "enroll_members",
    "review_visitors",
    "fix_camera_ingest",
    "upload_floor_plan",
    "draw_room_polygons",
    "calibrate_cameras",
    "enable_capture",
    "label_captures",
    "fit_and_deploy_artifact",
    "refit_artifact",
    "review_shadow",
    "set_policy_calibrated",
    "enable_templates",
    "review_body_samples",
    "configure_wearables",
    "resume_wearable_teaching",
    "enable_wearable_learners",
    "check_service",
]


class ReadinessStep(BaseModel):
    key: ReadinessStepKey
    state: ReadinessState
    detail: str = Field(description="One plain sentence or two; counts, never identity ids")
    next_action: ReadinessNextAction
    optional: bool = Field(
        default=False,
        description="An optional improvement: its state never blocks the steps after it",
    )


class ReviewQueue(BaseModel):
    """One identity review queue and how much waits in it."""

    surface: ReviewSurface
    waiting: int | None = Field(
        ge=0, description="Items waiting for a decision; null when the owner could not be read"
    )


class IdentityReadinessEnvelope(BaseModel):
    steps: list[ReadinessStep] = Field(description="In setup order")
    blocking_step: ReadinessStepKey | None = Field(
        description="The first required step that is blocked; null when none is"
    )
    review_queues: list[ReviewQueue] = Field(
        description=(
            "Every place an operator says who a face or body is, with its waiting count: "
            "recurring unrecognized faces, calibration captures, body samples"
        )
    )
    checked_at: datetime


class CTSGalleryCounts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pending_review: int = Field(ge=0)
    auto_verified: int = Field(ge=0)
    operator_verified: int = Field(ge=0)
    rejected: int = Field(ge=0)
    expired: int = Field(default=0, ge=0)


class CTSWearableLearnersReadiness(BaseModel):
    model_config = ConfigDict(extra="ignore")

    wearable_mode: str = "off"
    wearable_seeding_enabled: bool = False
    face_attestation_mode: str = "off"
    wearable_backfill_enabled: bool = False
    auto_on_swap: bool = True
    evaluation_sample_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    evaluation_days_14d: int = Field(default=0, ge=0)
    attribution_difference_14d: float | None = None
    open_teaching_holds: int = Field(default=0, ge=0)
    revoked_segments_14d: int = Field(default=0, ge=0)


class CTSCameraCalibration(BaseModel):
    model_config = ConfigDict(extra="ignore")

    camera_id: str
    calibrated: bool


class CTSClosedWorldReadiness(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: str = "off"
    active: bool = False
    inactive_reason: str | None = None
    roster_complete: bool | None = None
    visitors_present: bool | None = None
    presence_age_s: float | None = Field(default=None, ge=0.0)


class CTSIdentityReadiness(BaseModel):
    """The tracking orchestrator's ``GET /internal/identity/readiness`` response."""

    model_config = ConfigDict(extra="ignore")

    face_evidence_policy: str
    face_templates_mode: str
    face_quality_mode: str
    cc_assertion_mode: str
    wearable_mode: str = "off"
    closed_world_mode: str = "off"
    expected_arcface_model_version: str | None
    expected_quality_version: str
    reid_gallery_counts: CTSGalleryCounts | None
    # Rows a wearable taught, by state; absent from an orchestrator that predates them.
    wearable_gallery_counts: CTSGalleryCounts | None = None
    wearable_learners: CTSWearableLearnersReadiness | None = None
    closed_world: CTSClosedWorldReadiness | None = None
    cameras: list[CTSCameraCalibration]
    overlap_group_count: int | None
    identities_known: int | None
