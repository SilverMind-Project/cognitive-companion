from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BboxAnnotationResponse(BaseModel):
    id: str
    keyframe_id: str
    tracklet_id: str
    camera_id: str
    x1: float
    y1: float
    x2: float
    y2: float
    detection_confidence: float
    frame_width: int
    frame_height: int
    identity_id: str | None
    created_at: datetime
    # User override (None if no override)
    override_x1: float | None = None
    override_y1: float | None = None
    override_x2: float | None = None
    override_y2: float | None = None
    override_by: str | None = None
    override_at: datetime | None = None


class BboxOverrideRequest(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
