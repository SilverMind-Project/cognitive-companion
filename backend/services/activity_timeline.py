"""Unified activity timeline service.

Provides a chronological event feed combining:
- PersonActivity events
- ActivitySession open/close events
- PersonLocationHistory room transitions
- PersonSighting detections
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.core.time import UTC

logger = get_logger(__name__)


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
    - PersonLocationHistory: room transitions
    - PersonSighting: person detection events

    Events are sorted by timestamp descending (newest first).
    """

    def __init__(self, db_session_factory):
        """Initialize the service.

        Args:
            db_session_factory: Callable that returns a new DB Session.
        """
        self._db_session_factory = db_session_factory

    def get_timeline(
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
        db = self._db_session_factory()
        try:
            events: list[TimelineEvent] = []

            # Collect events from each source
            if not event_types or "activity" in event_types:
                events.extend(self._get_activity_events(db, person_id, start_time, end_time))

            if not event_types or "session" in event_types:
                events.extend(self._get_session_events(db, person_id, start_time, end_time))

            if not event_types or "location" in event_types:
                events.extend(self._get_location_events(db, person_id, start_time, end_time))

            if not event_types or "sighting" in event_types:
                events.extend(self._get_sighting_events(db, person_id, start_time, end_time))

            # Sort by timestamp descending
            events.sort(key=lambda e: e.timestamp, reverse=True)

            # Apply limit
            events = events[:limit]

            # Convert to dicts
            return [self._event_to_dict(e) for e in events]
        finally:
            db.close()

    def get_timeline_range(
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
        return self.get_timeline(
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

        stmt = select(PersonActivity).where(
            and_(
                PersonActivity.person_id == person_id,
                PersonActivity.detected_at >= (start_time or datetime.min.replace(tzinfo=UTC)),
                PersonActivity.detected_at <= (end_time or datetime.max.replace(tzinfo=UTC)),
            )
        ).order_by(PersonActivity.detected_at.desc())

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
        stmt = select(ActivitySession).where(*conditions).order_by(
            ActivitySession.opened_at.desc()
        )

        sessions = db.execute(stmt).scalars().all()

        events: list[TimelineEvent] = []
        for s in sessions:
            # Open event
            events.append(
                TimelineEvent(
                    timestamp=s.opened_at,
                    event_type="session_opened" if s.status == "open" else "session_opened_historic",
                    person_id=s.person_id,
                    person_name=None,
                    activity_type=s.activity_type,
                    room_name=s.room_name,
                    metadata={
                        "session_id": s.id,
                        "timeout_minutes": s.timeout_minutes,
                        "observation_id": s.observation_id,
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
                            "closed_via": s.metadata_json.get("closed_via", "unknown") if s.metadata_json else "unknown",
                        },
                        source="session",
                    )
                )

        return events

    def _get_location_events(
        self,
        db: Session,
        person_id: str,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> list[TimelineEvent]:
        """Get PersonLocationHistory room transition events."""
        from backend.models.person import PersonLocationHistory

        stmt = select(PersonLocationHistory).where(
            and_(
                PersonLocationHistory.person_id == person_id,
                PersonLocationHistory.entered_at >= (start_time or datetime.min.replace(tzinfo=UTC)),
                or_(
                    PersonLocationHistory.exited_at >= (start_time or datetime.min.replace(tzinfo=UTC)),
                    PersonLocationHistory.exited_at.is_(None),
                ),
            )
        ).order_by(PersonLocationHistory.entered_at.desc())

        histories = db.execute(stmt).scalars().all()

        return [
            TimelineEvent(
                timestamp=h.entered_at,
                event_type="room_entered" if h.exited_at is None else "room_transited",
                person_id=h.person_id,
                person_name=None,
                activity_type=None,
                room_name=h.room_name,
                metadata={
                    "from_room": h.from_room_name,
                    "direction": h.direction_semantic,
                    "exited_at": h.exited_at,
                    "source": h.source,
                },
                source="location",
            )
            for h in histories
        ]

    def _get_sighting_events(
        self,
        db: Session,
        person_id: str,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> list[TimelineEvent]:
        """Get PersonSighting detection events."""
        from backend.models.person import PersonSighting

        stmt = select(PersonSighting).where(
            and_(
                PersonSighting.person_id == person_id,
                PersonSighting.timestamp >= (start_time or datetime.min.replace(tzinfo=UTC)),
                PersonSighting.timestamp <= (end_time or datetime.max.replace(tzinfo=UTC)),
            )
        ).order_by(PersonSighting.timestamp.desc())

        sightings = db.execute(stmt).scalars().all()

        return [
            TimelineEvent(
                timestamp=s.timestamp,
                event_type="person_sighted",
                person_id=s.person_id,
                person_name=None,
                activity_type=None,
                room_name=s.room_name,
                metadata={
                    "confidence": s.confidence,
                    "sensor_id": s.sensor_id,
                    "direction": s.direction,
                    "bbox": s.bbox_json,
                    "source": s.source,
                },
                source="sighting",
            )
            for s in sightings
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
