from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AlertOut(BaseModel):
    id: int
    timestamp: datetime
    alert_type: str
    description: str
    sensor_id: str | None
    room_name: str | None
    resolved: bool
    assistance_needed: bool
    notification_sent_json: dict[str, Any] | None

    model_config = {"from_attributes": True}


class AlertAction(BaseModel):
    action: str  # "dismiss" or "assist"
