"""Face calibration review BFF envelopes.

person-identification-service owns the capture set: it samples faces from the tracker's identify
calls, stores the aligned crops, and enforces label rules. The BFF validates its envelopes,
presigns crops for the browser, and takes the labeler from the auth context. Embeddings never
reach this service or the browser.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

CalibrationLabelState = Literal["unlabeled", "labeled", "rejected"]
CalibrationLabelKind = Literal["member", "not_enrolled", "not_a_face"]


class CalibrationCandidateView(BaseModel):
    candidate_id: str
    captured_at: datetime
    camera_id: str
    crop_url: str | None = Field(None, description="Presigned aligned-crop URL; null if unsigned")
    quality_score: float = Field(..., ge=0.0, le=1.0)
    quality_version: str
    interocular_px: float | None = None
    yaw_deg: float
    pitch_deg: float
    nearest_person_id: str | None = None
    nearest_similarity: float = Field(
        ..., description="Raw cosine similarity to the nearest member; not a probability"
    )
    label_state: CalibrationLabelState
    label_kind: CalibrationLabelKind | None = None
    label_identity_id: str | None = None
    labeled_by: str | None = None
    labeled_at: datetime | None = None


class CalibrationCandidateListResponse(BaseModel):
    candidates: list[CalibrationCandidateView]
    next_cursor: str | None = None


class LabelCalibrationCandidateRequest(BaseModel):
    """The labeler is the authenticated caller; the browser never names one."""

    model_config = {"extra": "forbid"}

    label_kind: CalibrationLabelKind
    label_identity_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _identity_only_for_members(self) -> LabelCalibrationCandidateRequest:
        if (self.label_kind == "member") != (self.label_identity_id is not None):
            raise ValueError("label_identity_id is required for member labels and only for them")
        return self


class CalibrationIdentityProgressView(BaseModel):
    identity_id: str
    labeled_faces: int
    episodes: int
    target_labeled_faces: int


class FaceCalibrationSummaryEnvelope(BaseModel):
    """Labeling progress toward the calibration gates (counts only, no faces)."""

    by_state: dict[str, int]
    by_label_kind: dict[str, int]
    by_quality_decile: dict[str, int]
    by_camera: dict[str, int]
    identities: list[CalibrationIdentityProgressView]
    not_enrolled_episodes: int
    capture_enabled: bool
