"""Pydantic schemas for person tracking endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# -- Household Members --------------------------------------------------------

class HouseholdMemberCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    is_guest: bool = False
    metadata_json: dict | None = None


class HouseholdMemberUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    is_guest: bool | None = None
    metadata_json: dict | None = None


class HouseholdMemberOut(BaseModel):
    id: str
    name: str
    is_active: bool
    is_guest: bool
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime | None = None
    is_enrolled: bool = False
    embedding_count: int = 0

    model_config = {"from_attributes": True}


# -- Enrollment --------------------------------------------------------------


class PersonEnrollmentOut(BaseModel):
    person_id: str
    name: str
    embedding_count: int
    created_at: datetime


class EnrollResultOut(BaseModel):
    person_id: str
    name: str
    embedding_count: int
    status: str


# -- Person Sightings --------------------------------------------------------

class PersonSightingOut(BaseModel):
    id: int
    person_id: str
    sensor_id: str
    room_name: str | None = None
    timestamp: datetime
    confidence: float
    direction: str | None = None
    bbox_json: dict | None = None
    source: str

    model_config = {"from_attributes": True}


# -- Person Location ---------------------------------------------------------

class PersonLocationOut(BaseModel):
    person_id: str
    person_name: str
    current_room_name: str | None = None
    last_seen_at: datetime | None = None
    last_sensor_id: str | None = None
    status: str
    confidence: float

    model_config = {"from_attributes": True}


class PersonLocationHistoryOut(BaseModel):
    id: int
    person_id: str
    room_name: str | None = None
    entered_at: datetime
    exited_at: datetime | None = None
    source: str

    model_config = {"from_attributes": True}
