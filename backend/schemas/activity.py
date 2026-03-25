"""Pydantic schemas for person activity endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PersonActivityOut(BaseModel):
    id: int
    person_id: str
    activity_type: str
    room_name: str | None
    detected_at: datetime
    confidence: float

    model_config = {"from_attributes": True}
