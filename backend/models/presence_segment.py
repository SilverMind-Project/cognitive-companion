"""Presence segment ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.core.time import UTCDateTime


class PresenceSegment(Base):
    __tablename__ = "presence_segments"
    __table_args__ = (
        Index("idx_ps_person_open", "person_id", postgresql_where=text("exited_at IS NULL")),
        Index("idx_ps_person_time", "person_id", text("entered_at DESC")),
        Index("idx_ps_room_time", "room_id", text("entered_at DESC")),
        # identity-continuity M05: idempotency backstop for the backfill
        # projector under concurrent stream redelivery. A read-then-write
        # check alone is not enforcement; this partial unique index is.
        Index(
            "uq_ps_backfill_revision_entered",
            "backfill_revision_id",
            "entered_at",
            unique=True,
            postgresql_where=text("backfill_revision_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(UUID, primary_key=True)
    # household_members.id is String(64) and rooms.id is Integer per the
    # pre-existing schema (see alembic 0001_initial_schema).
    person_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("household_members.id"), nullable=False
    )
    room_id: Mapped[int] = mapped_column(Integer, ForeignKey("rooms.id"), nullable=False)
    entered_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    exited_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    entry_source: Mapped[str] = mapped_column(String(32), nullable=False)
    exit_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    quality: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    superseded_by: Mapped[str | None] = mapped_column(
        UUID, ForeignKey("presence_segments.id"), nullable=True
    )
    # identity-continuity M05: set only on segments inserted by the Unknown-
    # backfill projector. NULL for every ordinary (observed/inferred/manual)
    # segment. See the partial unique index above.
    backfill_revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
