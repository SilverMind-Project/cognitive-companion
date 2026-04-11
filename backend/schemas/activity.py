"""Pydantic schemas for person activity endpoints."""

from __future__ import annotations

from pydantic import BaseModel

from backend.schemas.common import UTCDatetime


class PersonActivityOut(BaseModel):
    id: int
    person_id: str
    activity_type: str
    room_name: str | None
    detected_at: UTCDatetime
    confidence: float

    model_config = {"from_attributes": True}
