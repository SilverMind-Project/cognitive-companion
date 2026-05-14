"""Pydantic schemas for CtsWindowTrigger CRUD endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CtsWindowTriggerBase(BaseModel):
    """Shared fields for CtsWindowTrigger."""

    name: str = Field(..., min_length=1, max_length=256)
    window_seconds: float = Field(10.0, ge=1.0, le=300.0)
    min_detections: int = Field(1, ge=0)
    min_identities: int = Field(1, ge=0)
    cameras: list[str] | None = None
    rooms: list[str] | None = None
    cooldown_seconds: float = Field(0.0, ge=0.0, le=3600.0)
    enabled: bool = True


class CtsWindowTriggerCreate(CtsWindowTriggerBase):
    """Payload for creating a new CTS window trigger."""


class CtsWindowTriggerUpdate(BaseModel):
    """Payload for updating an existing CTS window trigger.  All fields optional."""

    name: str | None = Field(None, min_length=1, max_length=256)
    window_seconds: float | None = Field(None, ge=1.0, le=300.0)
    min_detections: int | None = Field(None, ge=0)
    min_identities: int | None = Field(None, ge=0)
    cameras: list[str] | None = None
    rooms: list[str] | None = None
    cooldown_seconds: float | None = Field(None, ge=0.0, le=3600.0)
    enabled: bool | None = None


class CtsWindowTriggerOut(CtsWindowTriggerBase):
    """Response model for a CTS window trigger."""

    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
