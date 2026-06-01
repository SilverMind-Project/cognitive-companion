"""SQLAlchemy model for the first-class identity revision audit log.

Every identity decision (auto from the orchestrator resolver, manual from
corrections/merges) is recorded here.  This is separate from the
``superseded_by_revision_id`` flag on ``PersonLocationHistory`` which tracks
which individual history rows were rewritten by a revision.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.core.time import UTCDateTime


class CtsIdentityRevisionLog(Base):
    __tablename__ = "cts_identity_revision_log"
    __table_args__ = (
        Index("ix_cts_identity_revision_log_applied_at", text("applied_at DESC")),
        Index("ix_cts_identity_revision_log_ph_applied", "ph_id", text("applied_at DESC")),
        Index("ix_cts_identity_revision_log_kind_applied", "kind", text("applied_at DESC")),
    )

    revision_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    ph_id: Mapped[str] = mapped_column(String(128), nullable=False)
    previous_identity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    new_identity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    applied_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # auto | manual_correct | manual_merge
    rewritten_rows: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
