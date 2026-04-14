"""Person identification, sighting, and location tracking models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.core.time import UTCDateTime


class HouseholdMember(Base):
    """A registered member of the household."""

    __tablename__ = "household_members"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), onupdate=func.now(), nullable=True
    )

    sightings: Mapped[list[PersonSighting]] = relationship(back_populates="person")
    location_state: Mapped[PersonLocationState | None] = relationship(
        back_populates="person", uselist=False
    )


class PersonSighting(Base):
    """A single detection of a person by a camera or sensor."""

    __tablename__ = "person_sightings"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("household_members.id"), index=True
    )
    sensor_id: Mapped[str] = mapped_column(String(128), index=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    room_name: Mapped[str | None] = mapped_column(String(128))
    timestamp: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), index=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    direction: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bbox_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="camera")

    person: Mapped[HouseholdMember] = relationship(back_populates="sightings")


class PersonLocationState(Base):
    """Current inferred location of a person (one row per person)."""

    __tablename__ = "person_location_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("household_members.id"), unique=True, index=True
    )
    current_room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    current_room_name: Mapped[str | None] = mapped_column(String(128))
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_sensor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now()
    )

    person: Mapped[HouseholdMember] = relationship(back_populates="location_state")


class PersonLocationHistory(Base):
    """Room-level location timeline for a person.

    The ``direction_semantic`` / ``from_room_*`` fields are populated when a
    camera topology map is configured on the triggering sensor (see
    :mod:`backend.services.camera_topology`).  They are ``None`` for entries
    inferred from Home Assistant presence sensors or legacy camera events.
    """

    __tablename__ = "person_location_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("household_members.id"), index=True
    )
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    room_name: Mapped[str | None] = mapped_column(String(128))
    entered_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    exited_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="inferred")

    # Camera-topology-derived fields (nullable — absent on legacy rows).
    direction_semantic: Mapped[str | None] = mapped_column(String(32), nullable=True)
    from_room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    from_room_name: Mapped[str | None] = mapped_column(String(128), nullable=True)


class PersonActivity(Base):
    """Detected activity for a person (e.g. eating, sleeping, taking medication).

    Recorded by the ``activity_detection`` pipeline step and queried by
    ``person_activity`` context filters on downstream rules.
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

    person: Mapped[HouseholdMember] = relationship()
