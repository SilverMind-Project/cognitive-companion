from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EventLogOut(BaseModel):
    id: int
    timestamp: datetime
    rule_id: int | None
    rule_name: str | None
    sensor_id: str | None
    room_name: str | None
    trigger_type: str
    media_paths_json: list[str] | None
    pipeline_data_json: dict[str, Any] | None
    status: str

    model_config = {"from_attributes": True}
