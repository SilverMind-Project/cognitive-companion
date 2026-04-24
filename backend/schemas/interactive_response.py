"""Pydantic schemas for interactive response WebSocket messages."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.common import UTCDatetime


class InteractiveResponseMessage(BaseModel):
    """Schema for interactive_response WebSocket message from client."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "interactive_response",
                "execution_id": 123,
                "step_id": 456,
                "action": "escalate",
                "timestamp": "2024-01-15T10:30:15Z",
            }
        }
    )

    type: str = Field(..., description="Message type, must be 'interactive_response'")
    execution_id: int = Field(..., description="Workflow execution ID", gt=0)
    step_id: int = Field(..., description="Pipeline step ID", gt=0)
    action: str = Field(..., description="User action: escalate or dismiss")
    timestamp: UTCDatetime = Field(..., description="Response timestamp in ISO 8601 format")
