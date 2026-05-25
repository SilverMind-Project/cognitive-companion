"""Interactive response model for two-way user communication."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.core.time import UTCDateTime


class InteractiveResponse(Base):
    """Stores user responses to interactive prompts.

    This model tracks responses from various channels (popup, voice, timeout)
    to interactive prompts sent during pipeline execution. The unique constraint
    on (execution_id, step_id) ensures deduplication when multiple channels
    receive responses concurrently.
    """

    __tablename__ = "interactive_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("workflow_executions.id"), index=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("pipeline_steps.id"), index=True)
    channel: Mapped[str] = mapped_column(String(64))  # pwa_popup_text, pwa_realtime_ai, timeout
    action: Mapped[str] = mapped_column(String(32))  # escalate, dismiss
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    raw_response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), index=True
    )

    # Unique constraint for deduplication (first response wins)
    __table_args__ = (
        Index(
            "ix_interactive_responses_execution_step",
            "execution_id",
            "step_id",
            unique=True,
        ),
    )
