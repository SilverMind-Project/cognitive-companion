from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.schemas.common import OutSchema, UTCDatetime


class AlertOut(OutSchema):
    id: int
    timestamp: UTCDatetime
    alert_type: str
    description: str
    sensor_id: str | None
    room_name: str | None
    resolved: bool
    assistance_needed: bool
    notification_sent_json: dict[str, Any] | None


class AlertAction(BaseModel):
    action: str  # "dismiss" or "assist"
