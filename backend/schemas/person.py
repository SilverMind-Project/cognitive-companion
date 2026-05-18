"""Pydantic schemas for person tracking endpoints."""

from __future__ import annotations

from typing import Any

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
    metadata_json: dict | None = None
    cts_alert_config: dict[str, Any] | None = None


class HouseholdMemberUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    is_guest: bool | None = None
    metadata_json: dict | None = None
    cts_alert_config: dict[str, Any] | None = None


class HouseholdMemberOut(OutSchema):
    id: str
    name: str
    is_active: bool
    is_guest: bool
    metadata_json: dict | None = None
    cts_alert_config: dict[str, Any] | None = None
    created_at: UTCDatetime
    updated_at: OptionalUTCDatetime = None
    is_enrolled: bool = False
    embedding_count: int = 0


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


# -- Person Sightings --------------------------------------------------------


class PersonSightingOut(OutSchema):
    id: int
    person_id: str
    sensor_id: str
    room_name: str | None = None
    timestamp: UTCDatetime
    confidence: float
    direction: str | None = None
    bbox_json: dict | None = None
    source: str


# -- Person Location ---------------------------------------------------------


class PersonLocationOut(OutSchema):
    person_id: str
    person_name: str
    current_room_name: str | None = None
    last_seen_at: OptionalUTCDatetime = None
    last_sensor_id: str | None = None
    status: str
    confidence: float


class PersonLocationHistoryOut(OutSchema):
    id: int
    person_id: str
    room_name: str | None = None
    entered_at: UTCDatetime
    exited_at: OptionalUTCDatetime = None
    source: str
