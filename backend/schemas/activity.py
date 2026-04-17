"""Pydantic schemas for person activity endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.schemas.common import OptionalUTCDatetime, UTCDatetime


class PersonActivityOut(BaseModel):
    id: int
    person_id: str
    activity_type: str
    room_name: str | None
    detected_at: UTCDatetime
    confidence: float

    model_config = {"from_attributes": True}


# -- Activity Session Schemas -------------------------------------------------


class ActivitySessionOut(BaseModel):
    """Output schema for activity session."""

    session_id: str
    person_id: str
    activity_type: str
    room_name: str | None
    opened_at: UTCDatetime
    closed_at: OptionalUTCDatetime = None
    status: str
    timeout_minutes: int | None
    duration_minutes: int | None
    observation_id: int | None

    model_config = {"from_attributes": True}


class ActivitySessionOpenResult(BaseModel):
    """Result of opening an activity session."""

    session_id: str
    person_id: str
    activity_type: str
    room_name: str | None
    opened_at: UTCDatetime
    timeout_minutes: int | None
    was_existing: bool = False
    """True if a session already existed and was reused (idempotent open)."""


class ActivitySessionCloseResult(BaseModel):
    """Result of closing an activity session."""

    session_id: str
    person_id: str
    activity_type: str
    room_name: str | None
    opened_at: UTCDatetime
    closed_at: UTCDatetime
    duration_minutes: int
    status: str
    closed_via: str
    """One of: 'explicit', 'timeout', 'manual'."""


# -- Daily Report Schemas -----------------------------------------------------


class DailyReportOut(BaseModel):
    """Output schema for daily report."""

    person_id: str
    report_date: str
    tz_name: str
    generated_at: UTCDatetime
    sleep: dict[str, Any]
    meals: dict[str, Any]
    medication: dict[str, Any]
    bathroom_visits: dict[str, Any]
    door_events: dict[str, Any]
    exercise: dict[str, Any]
    room_time: dict[str, Any]
    summary_text: str | None
    wellness_score: float | None
    wellness_alerts: list[dict]
    room_trends: dict | None = None

    model_config = {"from_attributes": True}


class DailyReportQueryParams(BaseModel):
    """Query parameters for daily report generation."""

    include_llm_summary: bool = False
    include_room_trends: bool = False
    tz_name: str = "UTC"
