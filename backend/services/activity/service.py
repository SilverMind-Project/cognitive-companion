"""Activity domain service.

Consolidates :class:`~backend.services.person_tracking.PersonTrackingService.record_activity`
and :class:`~backend.services.activity_session.ActivitySessionService.open_session` /
`close_session` into a single domain service.

Delegates to the underlying services; no new persistence logic lives here.
This is the thin domain surface that pipeline steps call.
"""

from __future__ import annotations

from datetime import datetime

from backend.core.logging import get_logger
from backend.models.person import PersonActivity
from backend.services.activity.types import ActivityRecord, SessionRecord

logger = get_logger(__name__)


class ActivityService:
    """Domain service for person activities and activity sessions.

    Wraps :class:`~backend.services.person_tracking.PersonTrackingService`
    and :class:`~backend.services.activity_session.ActivitySessionService`
    so that pipeline steps call one named surface instead of reaching into
    two separate services.
    """

    def __init__(
        self,
        person_tracking: object,
        activity_session: object,
    ) -> None:
        self._person_tracking = person_tracking
        self._activity_session = activity_session

    # ------------------------------------------------------------------
    # Activity recording
    # ------------------------------------------------------------------

    async def record(
        self,
        *,
        person_id: str,
        activity_type: str,
        room_name: str | None,
        confidence: float,
        source_event_id: int | None = None,
        metadata: dict | None = None,
    ) -> ActivityRecord:
        """Record a detected activity for a person.

        Delegates to :meth:`~backend.services.person_tracking.PersonTrackingService.record_activity`
        and converts the ORM row to an :class:`ActivityRecord`.
        """
        orm: PersonActivity = await self._person_tracking.record_activity(
            person_id=person_id,
            activity_type=activity_type,
            room_name=room_name,
            confidence=confidence,
            source_event_id=source_event_id,
            metadata=metadata,
        )
        return ActivityRecord(
            id=orm.id,
            person_id=orm.person_id,
            activity_type=orm.activity_type,
            room_id=orm.room_id,
            room_name=orm.room_name,
            confidence=orm.confidence,
            source_event_id=orm.source_event_id,
            metadata_json=orm.metadata_json,
            duration_minutes=orm.duration_minutes,
            session_id=orm.session_id,
            detected_at=orm.detected_at,
        )

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def open_session(
        self,
        *,
        person_id: str,
        activity_type: str,
        room_name: str,
        confidence: float,
        started_at: datetime,
        start_event_id: int | None = None,
        timeout_minutes: int | None = None,
        metadata: dict | None = None,
    ) -> SessionRecord:
        """Open (or reuse) an activity session for a person.

        Delegates to :meth:`~backend.services.activity_session.ActivitySessionService.open_session`.
        """
        result = self._activity_session.open_session(
            person_id=person_id,
            activity_type=activity_type,
            room_name=room_name,
            confidence=confidence,
            started_at=started_at,
            start_event_id=start_event_id,
            timeout_minutes=timeout_minutes,
            metadata=metadata,
        )
        return SessionRecord(
            session_id=result.session_id,
            person_id=result.person_id,
            activity_type=result.activity_type,
            room_name=result.room_name,
            opened_at=result.opened_at,
            closed_at=None,
            duration_minutes=None,
            status="open",
            closed_via=None,
            timeout_minutes=result.timeout_minutes,
            was_existing=result.was_existing,
        )

    def close_session(
        self,
        *,
        person_id: str,
        activity_type: str,
        ended_at: datetime,
        end_event_id: int | None = None,
        closed_via: str = "explicit",
    ) -> SessionRecord:
        """Close an open activity session.

        Delegates to :meth:`~backend.services.activity_session.ActivitySessionService.close_session`.
        """
        result = self._activity_session.close_session(
            person_id=person_id,
            activity_type=activity_type,
            ended_at=ended_at,
            end_event_id=end_event_id,
            closed_via=closed_via,
        )
        return SessionRecord(
            session_id=result.session_id,
            person_id=result.person_id,
            activity_type=result.activity_type,
            room_name=result.room_name,
            opened_at=result.opened_at,
            closed_at=result.closed_at,
            duration_minutes=result.duration_minutes,
            status=result.status,
            closed_via=result.closed_via,
            timeout_minutes=None,
            was_existing=False,
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def query_recent(
        self,
        *,
        person_id: str | None = None,
        activity_type: str | None = None,
        since: datetime,
    ) -> list[ActivityRecord]:
        """Return recent activity records for a person.

        Delegates to :meth:`~backend.services.person_tracking.PersonTrackingService.get_recent_activities`.
        """
        from backend.core.time import UTC

        minutes = max(1, int((datetime.now(UTC) - since).total_seconds() / 60))
        rows = await self._person_tracking.get_recent_activities(
            person_id=person_id or "",
            activity_type=activity_type,
            minutes=minutes,
        )
        return [
            ActivityRecord(
                id=row["id"],
                person_id=row["person_id"],
                activity_type=row["activity_type"],
                room_id=None,
                room_name=row["room_name"],
                confidence=row["confidence"],
                source_event_id=None,
                metadata_json=None,
                duration_minutes=None,
                session_id=None,
                detected_at=None,
            )
            for row in rows
        ]
