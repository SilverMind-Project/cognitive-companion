"""Guided-task routine, session, and event models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.core.time import UTCDateTime


class Routine(Base):
    """A linear guided task script for one household member."""

    __tablename__ = "routines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    person_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("household_members.id"), index=True, nullable=False
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    language_override: Mapped[str | None] = mapped_column(String(16), nullable=True)
    voice_override: Mapped[str | None] = mapped_column(String(64), nullable=True)
    system_instruction_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_timeout_s_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_step_attempts_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resume_grace_s_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalation_channels_override: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    summon_channels_override: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    rephrase_via_override: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    steps: Mapped[list[RoutineStep]] = relationship(
        back_populates="routine",
        cascade="all, delete-orphan",
        order_by="RoutineStep.ord",
    )
    sessions: Mapped[list[GuidedSession]] = relationship(back_populates="routine")


class RoutineStep(Base):
    """One ordered step inside a guided routine."""

    __tablename__ = "routine_steps"
    __table_args__ = (UniqueConstraint("routine_id", "ord", name="uq_routine_step_ord"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    routine_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("routines.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    completion_gate: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=lambda: {"kinds": ["response"]}
    )
    skip_condition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    camera_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    # M6 adds the foreign key to room_zones. M3 keeps this as a nullable integer
    # to avoid a forward migration dependency.
    zone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step_timeout_s_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_step_attempts_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_safety_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    routine: Mapped[Routine] = relationship(back_populates="steps")


class GuidedSession(Base):
    """One runtime execution of a guided routine."""

    __tablename__ = "guided_sessions"
    __table_args__ = (
        Index(
            "ix_guided_sessions_live_person",
            "person_id",
            postgresql_where=text(
                "status IN ('active', 'waiting', 'summoning', 'escalated', 'caregiver_takeover')"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    routine_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("routines.id"), index=True, nullable=False
    )
    person_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    execution_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    surface_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    current_step_ord: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)

    routine: Mapped[Routine] = relationship(back_populates="sessions")
    events: Mapped[list[GuidedSessionEvent]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="GuidedSessionEvent.at",
    )


class GuidedSessionEvent(Base):
    """Auditable guided-session timeline event."""

    __tablename__ = "guided_session_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guided_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    step_ord: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor: Mapped[str | None] = mapped_column(String(24), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    session: Mapped[GuidedSession] = relationship(back_populates="events")
