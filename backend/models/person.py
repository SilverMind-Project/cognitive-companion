"""Person identification, sighting, and location tracking models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base, TimestampMixin
from backend.core.time import UTCDateTime


class ActivityTypeEnum(StrEnum):
    """Activity types supported by the duration-aware session model."""

    sleep = "sleep"
    meal_prep = "meal_prep"
    meal_eating = "meal_eating"
    bathroom = "bathroom"
    exercise = "exercise"
    cooking = "cooking"
    medication = "medication"
    watching_tv = "watching_tv"
    reading = "reading"
    phone_call = "phone_call"
    other = "other"


class ActivitySourceEnum(StrEnum):
    """How an activity-session row was produced.

    The evidence grade a caregiver-facing answer is phrased against: a routine
    the resident completed step-by-step with the companion supports "she took
    her medication with me at 9:05"; a camera inference supports only "she was
    near the medicine cabinet".
    """

    guided_companion = "guided_companion"
    """Confirmed step-by-step during a completed guided routine (highest)."""

    ha_state_join = "ha_state_join"
    """Derived by joining Home Assistant entity state with presence."""

    sensor = "sensor"
    """Reported by a physical sensor."""

    vision_inferred = "vision_inferred"
    """Inferred from camera analysis (lowest; never proves an action)."""


class DailyReportStatus(StrEnum):
    """Status of a daily report generation."""

    pending = "pending"
    generating = "generating"
    complete = "complete"
    failed = "failed"


class HouseholdMember(Base, TimestampMixin):
    __tablename__ = "household_members"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False)
    alert_priority: Mapped[int] = mapped_column(Integer, default=5)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Per-person CTS alert configuration. Keys: enabled_kinds (list[str]), min_severity (str).
    # NULL means "use the default profile" (all kinds, info severity).
    cts_alert_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    activity_sessions: Mapped[list[ActivitySession]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    daily_reports: Mapped[list[DailyReport]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )


class PersonActivity(Base):
    """Detected activity for a person (e.g. eating, sleeping, taking medication).

    Recorded by the ``activity_detection`` pipeline step and queried by
    ``person_activity`` context filters on downstream rules.

    This model has been extended to support duration-aware activity sessions:
    - ``duration_minutes``: computed when session closes (sleep: 720min, bathroom: 90min, etc.)
    - ``session_id``: links to ActivitySession when activity is session-based
    - ``observation_id``: backlinks to scene_observations for auditability chain
    """

    __tablename__ = "person_activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("household_members.id"), index=True
    )
    activity_type: Mapped[str] = mapped_column(String(64), index=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    room_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), index=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_event_id: Mapped[int | None] = mapped_column(ForeignKey("event_logs.id"), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Duration-aware session fields (added via column migration)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Observation backlink for auditability chain (scene_observations table not yet created)
    observation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    person: Mapped[HouseholdMember] = relationship()


class ActivitySession(Base):
    """Duration-aware activity session with open/close lifecycle.

    Supports configurable timeouts per activity type:
    - sleep: 720 minutes (12 hours)
    - bathroom: 90 minutes
    - meal_prep / meal_eating: 90 minutes
    - exercise / cooking: 120 minutes

    Sessions are opened idempotently by pipeline steps and closed by either
    explicit end events or timeout sweeper. Duration is computed on close.

    The ``observation_id`` field backlinks to scene_observations when the
    session was triggered by a visual detection, enabling the auditability
    chain: PersonActivity → ActivitySession → scene_observation → workflow_execution.
    """

    __tablename__ = "activity_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    person_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("household_members.id"), index=True, nullable=False
    )
    activity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    room_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    timeout_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_event_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("event_logs.id"), nullable=True
    )
    close_event_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("event_logs.id"), nullable=True
    )

    # How this row was produced, and how much to trust it. A caregiver-facing
    # answer is phrased to match its evidence grade: a session confirmed
    # step-by-step with the resident is not the same claim as one inferred from
    # a camera, and a false "she took her medication" is a care-safety hazard.
    # ``source`` mirrors ``PersonActivity.confidence``'s precedent of keeping
    # provenance on the row rather than in a metadata blob.
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="vision_inferred", index=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")

    # ``MutableDict.as_mutable`` is required: close_session/close_timed_out_sessions
    # write ``closed_via`` into this dict in place. With a plain JSON column
    # SQLAlchemy only detects attribute *replacement*, so an in-place write to an
    # already-populated dict is silently discarded at flush.
    metadata_json: Mapped[dict | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )

    # Observation backlink for auditability chain (scene_observations table not yet created)
    observation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Relationships
    person: Mapped[HouseholdMember] = relationship(back_populates="activity_sessions")


class DailyReport(Base):
    """End-of-day structured summary report for a person.

    Generated at midnight local time (configurable via app.timezone) or
    on-demand. Aggregates:
    - Sleep duration and quality metrics
    - Meal occurrences (prep + eating)
    - Medication adherence
    - Bathroom visits (count, total duration)
    - Door events (open/close count)
    - Exercise sessions
    - Room location time distribution
    - Optional LLM-generated prose summary
    - Wellness score and alert flags

    The report is idempotently generated - calling generate_daily_report
    for an existing date/person will update the report if data changed.
    """

    __tablename__ = "daily_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    person_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("household_members.id"), index=True, nullable=False
    )
    report_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Sleep summary
    sleep_total_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sleep_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-1
    sleep_disruptions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Meal summary
    meal_prep_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meal_eating_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meal_avg_duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Medication adherence
    medication_doses_taken: Mapped[int | None] = mapped_column(Integer, nullable=True)
    medication_doses_due: Mapped[int | None] = mapped_column(Integer, nullable=True)
    medication_adherence_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100

    # Bathroom visits
    bathroom_visit_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathroom_total_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathroom_avg_duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Door events (unused; drop with the next schema tidy)
    door_open_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    door_close_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Exercise
    exercise_session_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exercise_total_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Room time distribution (JSON: {room_name: minutes})
    room_time_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # LLM-generated prose summary
    summary_text: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    summary_created_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    # Wellness score (0-100) and alert flags
    wellness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    wellness_alerts_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

    # Index for efficient queries
    __table_args__ = (
        # Unique index: one report per person per day
        UniqueConstraint("person_id", "report_date", name="uix_person_date"),
    )

    # Relationships
    person: Mapped[HouseholdMember] = relationship(back_populates="daily_reports")
