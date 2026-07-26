"""Unified activity timeline service.

Provides a chronological event feed combining:
- PersonActivity events
- ActivitySession open/close events
- PersonLocationService room-presence segments (M32: the sole
  person-location read API; replaces PersonLocationHistory)
- PersonLocationService raw observations (M32; replaces PersonSighting)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.core.time import UTC
from backend.services.person_location.types import LocationObservation, RoomSegment

logger = get_logger(__name__)


class PersonLocationReader(Protocol):
    async def room_segments(
        self, person_id: str, start: datetime, end: datetime
    ) -> tuple[RoomSegment, ...]: ...
    async def bucketed_observations(
        self, person_id: str, start: datetime, end: datetime, *, bucket_seconds: int = 120
    ) -> tuple[LocationObservation, ...]: ...


@dataclass
class TimelineEvent:
    """A single event in the unified timeline."""

    timestamp: datetime
    event_type: str
    person_id: str
    person_name: str | None
    activity_type: str | None
    room_name: str | None
    metadata: dict
    source: str
    """One of: 'activity', 'session', 'location', 'sighting'."""


class ActivityTimelineService:
    """Service for generating unified chronological event feeds.

    This service combines multiple data sources into a single timeline:
    - PersonActivity: detected activities (sleep, meals, etc.)
    - ActivitySession: session open/close events
    - PersonLocationService.room_segments: room transitions
    - PersonLocationService.observations: person detection events

    Events are sorted by timestamp descending (newest first).
    """

    def __init__(
        self,
        db_session_factory,
        person_location_service: PersonLocationReader | None = None,
    ):
        """Initialize the service.

        Args:
            db_session_factory: Callable that returns a new DB Session.
            person_location_service: Backs the location/sighting sources.
                ``None`` when CTS is disabled (bootstrap sets it later via
                ``set_person_location_service`` once the CTS phase runs);
                those two sources degrade to empty lists rather than erroring.
        """
        self._db_session_factory = db_session_factory
        self._person_location = person_location_service

    def set_person_location_service(
        self, person_location_service: PersonLocationReader | None
    ) -> None:
        self._person_location = person_location_service

    async def get_timeline(
        self,
        person_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        event_types: list[str] | None = None,
    ) -> list[dict]:
        """Get unified timeline events for a person.

        Args:
            person_id: Household member ID.
            start_time: Optional start time (UTC).
            end_time: Optional end time (UTC).
            limit: Maximum number of events to return.
            event_types: Optional filter by source type ('activity', 'session', 'location', 'sighting').

        Returns:
            List of timeline event dicts sorted by timestamp descending.
        """
        events: list[TimelineEvent] = []

        db = self._db_session_factory()
        try:
            # Collect events from each source
            if not event_types or "activity" in event_types:
                events.extend(self._get_activity_events(db, person_id, start_time, end_time))

            if not event_types or "session" in event_types:
                events.extend(self._get_session_events(db, person_id, start_time, end_time))
        finally:
            db.close()

        if not event_types or "location" in event_types:
            events.extend(await self._get_location_events(person_id, start_time, end_time))

        if not event_types or "sighting" in event_types:
            events.extend(await self._get_sighting_events(person_id, start_time, end_time))

        # Sort by timestamp descending
        events.sort(key=lambda e: e.timestamp, reverse=True)

        # Apply limit
        events = events[:limit]

        # Convert to dicts
        return [self._event_to_dict(e) for e in events]

    async def get_timeline_range(
        self,
        person_id: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 500,
    ) -> list[dict]:
        """Get timeline events for a specific time range.

        Convenience method for fetching a bounded time window.

        Args:
            person_id: Household member ID.
            start_time: Start of range (UTC).
            end_time: End of range (UTC).
            limit: Maximum events to return.

        Returns:
            List of timeline event dicts.
        """
        return await self.get_timeline(
            person_id=person_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    def _get_activity_events(
        self,
        db: Session,
        person_id: str,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> list[TimelineEvent]:
        """Get PersonActivity events."""
        from backend.models.person import PersonActivity

        stmt = (
            select(PersonActivity)
            .where(
                and_(
                    PersonActivity.person_id == person_id,
                    PersonActivity.detected_at >= (start_time or datetime.min.replace(tzinfo=UTC)),
                    PersonActivity.detected_at <= (end_time or datetime.max.replace(tzinfo=UTC)),
                )
            )
            .order_by(PersonActivity.detected_at.desc())
        )

        activities = db.execute(stmt).scalars().all()

        return [
            TimelineEvent(
                timestamp=a.detected_at,
                event_type="activity_detected",
                person_id=a.person_id,
                person_name=None,  # TODO: join with HouseholdMember
                activity_type=a.activity_type,
                room_name=a.room_name,
                metadata={
                    "confidence": a.confidence,
                    "source_event_id": a.source_event_id,
                    "observation_id": a.observation_id,
                    "metadata": a.metadata_json,
                },
                source="activity",
            )
            for a in activities
        ]

    def _get_session_events(
        self,
        db: Session,
        person_id: str,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> list[TimelineEvent]:
        """Get ActivitySession open/close events."""
        from backend.models.person import ActivitySession

        conditions = [
            ActivitySession.person_id == person_id,
            ActivitySession.opened_at >= (start_time or datetime.min.replace(tzinfo=UTC)),
        ]
        if end_time:
            conditions.append(ActivitySession.closed_at <= end_time)
        stmt = select(ActivitySession).where(*conditions).order_by(ActivitySession.opened_at.desc())

        sessions = db.execute(stmt).scalars().all()

        events: list[TimelineEvent] = []
        for s in sessions:
            # Open event
            events.append(
                TimelineEvent(
                    timestamp=s.opened_at,
                    event_type="session_opened"
                    if s.status == "open"
                    else "session_opened_historic",
                    person_id=s.person_id,
                    person_name=None,
                    activity_type=s.activity_type,
                    room_name=s.room_name,
                    metadata={
                        "session_id": s.id,
                        "timeout_minutes": s.timeout_minutes,
                        "observation_id": s.observation_id,
                        "evidence_source": s.source,
                        "confidence": s.confidence,
                    },
                    source="session",
                )
            )

            # Close event
            if s.closed_at and s.status == "closed":
                events.append(
                    TimelineEvent(
                        timestamp=s.closed_at,
                        event_type="session_closed",
                        person_id=s.person_id,
                        person_name=None,
                        activity_type=s.activity_type,
                        room_name=s.room_name,
                        metadata={
                            "session_id": s.id,
                            "duration_minutes": s.duration_minutes,
                            "closed_via": s.metadata_json.get("closed_via", "unknown")
                            if s.metadata_json
                            else "unknown",
                            "evidence_source": s.source,
                            "confidence": s.confidence,
                        },
                        source="session",
                    )
                )

        return events

    async def _get_location_events(
        self,
        person_id: str,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> list[TimelineEvent]:
        """Get room-presence segment events from PersonLocationService.

        Backed by ``room_segments`` (M32), not the legacy
        ``PersonLocationHistory`` table. Room transitions the CTS
        world-tracker records but the legacy table never fed are new
        entries here -- an enumerated correctness delta, not breakage.
        """
        if self._person_location is None:
            return []

        start = start_time or datetime.min.replace(tzinfo=UTC)
        end = end_time or datetime.max.replace(tzinfo=UTC)
        segments = await self._person_location.room_segments(person_id, start, end)

        return [
            TimelineEvent(
                timestamp=seg.entered_at,
                event_type="room_entered" if seg.exited_at is None else "room_transited",
                person_id=seg.person_id,
                person_name=None,
                activity_type=None,
                room_name=seg.room_name,
                metadata={
                    "from_room": seg.metadata.get("from_room"),
                    "direction": seg.metadata.get("direction"),
                    "exited_at": seg.exited_at,
                    "source": seg.entry_source,
                },
                source="location",
            )
            for seg in segments
        ]

    # world_tracker can ingest several raw observations a second (see
    # tracking-orchestrator's live_publish_max_hz, 3Hz per camera by
    # default) -- far denser than the legacy PersonSighting table this
    # source replaces (written once per identification run). Sighting
    # events are downsampled to one per room per this bucket width so a
    # dense stream can't drown out every other timeline source once merged.
    _SIGHTING_BUCKET_SECONDS = 120

    async def _get_sighting_events(
        self,
        person_id: str,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> list[TimelineEvent]:
        """Get downsampled observation events from PersonLocationService.

        Backed by ``bucketed_observations`` (M32), not the legacy
        ``PersonSighting`` table. Covers every SSOT observation source
        (``world_tracker``, ``face_sighting``, ...), not just the legacy
        step-driven path -- an enumerated correctness delta, not breakage.
        """
        if self._person_location is None:
            return []

        start = start_time or datetime.min.replace(tzinfo=UTC)
        end = end_time or datetime.max.replace(tzinfo=UTC)
        obs = await self._person_location.bucketed_observations(
            person_id, start, end, bucket_seconds=self._SIGHTING_BUCKET_SECONDS
        )

        return [
            TimelineEvent(
                timestamp=o.observed_at,
                event_type="person_sighted",
                person_id=o.person_id,
                person_name=None,
                activity_type=None,
                room_name=o.room_name,
                metadata={
                    "confidence": o.confidence,
                    "sensor_id": o.metadata.get("camera_id"),
                    "direction": None,
                    "bbox": None,
                    "source": o.source,
                },
                source="sighting",
            )
            for o in obs
        ]

    def _event_to_dict(self, event: TimelineEvent) -> dict:
        """Convert TimelineEvent to dict for API response."""
        return {
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            "event_type": event.event_type,
            "person_id": event.person_id,
            "person_name": event.person_name,
            "activity_type": event.activity_type,
            "room_name": event.room_name,
            "metadata": event.metadata,
            "source": event.source,
        }
