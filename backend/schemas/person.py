"""Pydantic schemas for person tracking endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from backend.schemas.common import OptionalUTCDatetime, OutSchema, UTCDatetime
from backend.services.cts.signal_config import ALL_SIGNAL_KINDS

# -- Household Members --------------------------------------------------------

_VALID_SEVERITIES = frozenset({"info", "warning", "emergency"})


class CtsAlertConfig(BaseModel):
    """Per-person CTS alert configuration embedded in HouseholdMember."""

    enabled_kinds: list[str] = Field(default_factory=lambda: list(ALL_SIGNAL_KINDS))
    min_severity: str = "info"

    @field_validator("enabled_kinds")
    @classmethod
    def _validate_kinds(cls, v: list[str]) -> list[str]:
        invalid = set(v) - set(ALL_SIGNAL_KINDS)
        if invalid:
            raise ValueError(f"Unknown signal kinds: {sorted(invalid)}")
        return v

    @field_validator("min_severity")
    @classmethod
    def _validate_severity(cls, v: str) -> str:
        if v not in _VALID_SEVERITIES:
            raise ValueError(f"min_severity must be one of {sorted(_VALID_SEVERITIES)}")
        return v


class HouseholdMemberCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    is_guest: bool = False
    height_cm: float | None = Field(default=None, ge=90.0, le=220.0)
    metadata_json: dict | None = None
    cts_alert_config: dict[str, Any] | None = None


class HouseholdMemberUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    is_guest: bool | None = None
    height_cm: float | None = Field(default=None, ge=90.0, le=220.0)
    metadata_json: dict | None = None
    cts_alert_config: dict[str, Any] | None = None


class HouseholdMemberOut(OutSchema):
    id: str
    name: str
    is_active: bool
    is_guest: bool
    height_cm: float | None = Field(default=None, ge=90.0, le=220.0)
    metadata_json: dict | None = None
    cts_alert_config: dict[str, Any] | None = None
    created_at: UTCDatetime
    updated_at: OptionalUTCDatetime = None
    is_enrolled: bool = False
    embedding_count: int = 0


class PersonHeightSyncItem(BaseModel):
    """Minimal member standing-height entry synced to CTS."""

    person_id: str
    height_cm: float | None = None


class PersonHeightProfileOut(BaseModel):
    """Combined operator-entered height and CTS effective standing height profile."""

    person_id: str
    operator_height_cm: float | None = None
    effective_height_m: float | None = None
    effective_sigma_m: float | None = None
    source: Literal["operator", "learned"] | None = None
    samples: int = 0
    cameras: int = 0
    updated_at: OptionalUTCDatetime = None
    cts_available: bool = True


# -- Enrollment --------------------------------------------------------------


class PersonEnrollmentOut(BaseModel):
    person_id: str
    name: str
    embedding_count: int
    created_at: UTCDatetime


class EnrollResultOut(BaseModel):
    person_id: str
    name: str
    embedding_count: int
    status: str


# -- Face Prototypes ---------------------------------------------------------


class PersonPrototypeView(BaseModel):
    """One face gallery prototype with a presigned thumbnail URL (never a raw storage key)."""

    prototype_id: str
    person_id: str
    pose_bin: str
    member_count: int
    source: str
    quality_score: float | None = None
    quality_version: str | None = None
    crop_url: str | None = Field(
        None, description="Presigned aligned-crop URL; null when no crop is stored or unsigned"
    )
    approved_by: str | None = None
    approved_at: OptionalUTCDatetime = None
    created_at: OptionalUTCDatetime = None


class PersonPrototypesResponse(BaseModel):
    person_id: str
    gallery_revision: int
    prototypes: list[PersonPrototypeView]
    counts_by_bin: dict[str, int] = Field(default_factory=dict)


class RebuildPrototypesResponse(BaseModel):
    person_id: str
    prototype_count: int
    counts_by_bin: dict[str, int] = Field(default_factory=dict)
