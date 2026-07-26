"""Duration-aware activity session service with open/close lifecycle.

Supports configurable timeouts per activity type:
- sleep: 720 minutes (12 hours)
- bathroom: 90 minutes
- meal_prep / meal_eating: 90 minutes
- exercise / cooking: 120 minutes

Sessions are opened idempotently and closed by explicit end events or timeout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select

from backend.core.logging import get_logger
from backend.core.time import UTC

logger = get_logger(__name__)


# Activity type timeout configuration (in minutes)
# These are the maximum durations before a session is auto-closed as timed out
ACTIVITY_TIMEOUTS: dict[str, int] = {
    "sleep": 720,  # 12 hours
    "bathroom": 90,  # 1.5 hours
    "meal_prep": 90,  # 1.5 hours
    "meal_eating": 90,  # 1.5 hours
    "exercise": 120,  # 2 hours
    "cooking": 120,  # 2 hours
    "medication": 30,  # 30 minutes
    "watching_tv": 180,  # 3 hours
    "reading": 120,  # 2 hours
    "phone_call": 60,  # 1 hour
    "other": 120,  # 2 hours default
}


@dataclass
class OpenSessionResult:
    """Result of opening an activity session."""

    session_id: str
    person_id: str
    activity_type: str
    room_name: str | None
    opened_at: datetime
    timeout_minutes: int | None
    source: str = "vision_inferred"
    """Provenance of the row (``ActivitySourceEnum``)."""
    confidence: float = 0.0
    was_existing: bool = False
    """True if a session already existed and was reused (idempotent open)."""


@dataclass
class CloseSessionResult:
    """Result of closing an activity session."""

    session_id: str
    person_id: str
    activity_type: str
    room_name: str | None
    opened_at: datetime
    closed_at: datetime
    duration_minutes: int
    status: str
    closed_via: str
    """One of: 'explicit', 'timeout', 'manual'."""
    source: str = "vision_inferred"
    """Provenance carried over from the opened row."""
    confidence: float = 0.0


class ActivitySessionService:
    """Service for managing duration-aware activity sessions.

    This service provides:
    - Idempotent session opening (reuses existing open session if same type)
    - Explicit session closing with duration computation
    - Timeout-based auto-closing for duration-aware activities
    - Query helpers for open sessions and daily sessions
    """

    def __init__(self, db_session_factory):
        """Initialize the service.

        Args:
            db_session_factory: Callable that returns a new DB Session.
        """
        self._db_session_factory = db_session_factory

    def open_session(
        self,
        person_id: str,
        activity_type: str,
        room_name: str | None,
        confidence: float,
        started_at: datetime,
        start_event_id: int | None,
        source: str = "vision_inferred",
        timeout_minutes: int | None = None,
        metadata: dict | None = None,
        observation_id: int | None = None,
    ) -> OpenSessionResult:
        """Open (or reuse) an activity session for a person.

        Idempotent: if an open session of the same type exists, returns it
        without creating a duplicate. This allows multiple detection events
        during the same activity to all trigger the same session open.

        Args:
            person_id: Household member ID.
            activity_type: One of ActivityTypeEnum values.
            room_name: Room where activity occurred.
            confidence: Detection confidence (0-1), clamped to that range.
            started_at: When the activity started (UTC).
            start_event_id: Source event log ID for auditability.
            source: How this row was produced (``ActivitySourceEnum``). An
                unrecognized value degrades to ``vision_inferred``, the lowest
                grade, so a typo can never inflate an answer's confidence.
            timeout_minutes: Override timeout (uses default if None).
            metadata: Additional session metadata.
            observation_id: Scene observation ID for audit chain.

        Returns:
            OpenSessionResult with session details.
        """
        db = self._db_session_factory()
        try:
            from backend.models.person import (
                ActivitySession,
                ActivitySourceEnum,
                ActivityTypeEnum,
                HouseholdMember,
            )

            # Ensure person exists (FK constraint)
            person = db.get(HouseholdMember, person_id)
            if not person:
                person = HouseholdMember(id=person_id, name="Unknown", is_active=True)
                db.add(person)
                db.commit()

            # Normalize activity type
            try:
                activity_type = ActivityTypeEnum(activity_type).value
            except ValueError:
                activity_type = "other"

            # Normalize provenance and confidence. Both degrade toward the
            # weakest claim rather than raising: a detector writing a bad
            # source string should still record the activity, just without
            # borrowing an evidence grade it cannot support.
            try:
                source = ActivitySourceEnum(source).value
            except ValueError:
                logger.warning(
                    "activity_session_unknown_source",
                    person_id=person_id,
                    activity_type=activity_type,
                    source=source,
                )
                source = ActivitySourceEnum.vision_inferred.value
            confidence = min(1.0, max(0.0, float(confidence)))

            # Check for existing open session of same type
            existing = db.execute(
                select(ActivitySession).where(
                    and_(
                        ActivitySession.person_id == person_id,
                        ActivitySession.activity_type == activity_type,
                        ActivitySession.status == "open",
                    )
                )
            ).scalar_one_or_none()

            if existing:
                logger.info(
                    "activity_session_open_idempotent",
                    person_id=person_id,
                    activity_type=activity_type,
                    session_id=existing.id,
                )
                # Reuse reports the *stored* provenance, not this call's:
                # the row belongs to whichever detector opened it, and a later
                # weaker sighting must not appear to restate it.
                return OpenSessionResult(
                    session_id=existing.id,
                    person_id=person_id,
                    activity_type=activity_type,
                    room_name=existing.room_name,
                    opened_at=existing.opened_at,
                    timeout_minutes=existing.timeout_minutes,
                    source=existing.source,
                    confidence=existing.confidence,
                    was_existing=True,
                )

            # Compute timeout
            effective_timeout = timeout_minutes or ACTIVITY_TIMEOUTS.get(
                activity_type, ACTIVITY_TIMEOUTS["other"]
            )

            # Generate session ID
            session_id = f"{person_id}_{activity_type}_{started_at.isoformat()}"

            # Create new session
            session = ActivitySession(
                id=session_id,
                person_id=person_id,
                activity_type=activity_type,
                room_id=None,  # TODO: resolve room_id from room_name
                room_name=room_name,
                opened_at=started_at,
                closed_at=None,
                status="open",
                timeout_minutes=effective_timeout,
                duration_minutes=None,
                open_event_id=start_event_id,
                close_event_id=None,
                source=source,
                confidence=confidence,
                metadata_json=metadata,
                observation_id=observation_id,
            )

            db.add(session)
            db.commit()

            logger.info(
                "activity_session_opened",
                person_id=person_id,
                activity_type=activity_type,
                session_id=session_id,
                timeout_minutes=effective_timeout,
                room_name=room_name,
                source=source,
                confidence=confidence,
            )

            return OpenSessionResult(
                session_id=session_id,
                person_id=person_id,
                activity_type=activity_type,
                room_name=room_name,
                opened_at=started_at,
                timeout_minutes=effective_timeout,
                source=source,
                confidence=confidence,
                was_existing=False,
            )
        except Exception:
            logger.exception("activity_session_open_error", person_id=person_id)
            db.rollback()
            raise
        finally:
            db.close()

    def close_session(
        self,
        person_id: str,
        activity_type: str,
        ended_at: datetime,
        end_event_id: int | None,
        closed_via: str = "explicit",
        observation_id: int | None = None,
    ) -> CloseSessionResult:
        """Close an open activity session.

        Args:
            person_id: Household member ID.
            activity_type: Activity type to close.
            ended_at: When the activity ended (UTC).
            end_event_id: Source event log ID for auditability.
            closed_via: One of 'explicit', 'timeout', 'manual'.
            observation_id: Scene observation ID for audit chain.

        Returns:
            CloseSessionResult with duration and status.

        Raises:
            ValueError: If no open session exists for this person/activity.
        """
        db = self._db_session_factory()
        try:
            from backend.models.person import ActivitySession

            # Find open session
            session = db.execute(
                select(ActivitySession).where(
                    and_(
                        ActivitySession.person_id == person_id,
                        ActivitySession.activity_type == activity_type,
                        ActivitySession.status == "open",
                    )
                )
            ).scalar_one_or_none()

            if not session:
                raise ValueError(f"No open session found for {person_id} / {activity_type}")

            # Compute duration
            duration_seconds = (ended_at - session.opened_at).total_seconds()
            duration_minutes = max(1, int(duration_seconds / 60))  # At least 1 minute

            # Update session
            session.closed_at = ended_at
            session.status = "closed"
            session.duration_minutes = duration_minutes
            session.close_event_id = end_event_id
            session.metadata_json = {**(session.metadata_json or {}), "closed_via": closed_via}
            if observation_id:
                session.observation_id = observation_id

            db.add(session)
            db.commit()

            logger.info(
                "activity_session_closed",
                person_id=person_id,
                activity_type=activity_type,
                session_id=session.id,
                duration_minutes=duration_minutes,
                closed_via=closed_via,
            )

            return CloseSessionResult(
                session_id=session.id,
                person_id=person_id,
                activity_type=activity_type,
                room_name=session.room_name,
                opened_at=session.opened_at,
                closed_at=session.closed_at,
                duration_minutes=duration_minutes,
                status=session.status,
                closed_via=closed_via,
                source=session.source,
                confidence=session.confidence,
            )
        except Exception:
            logger.exception("activity_session_close_error", person_id=person_id)
            db.rollback()
            raise
        finally:
            db.close()

    def close_timed_out_sessions(self, now: datetime | None = None) -> list[CloseSessionResult]:
        """Close all sessions that have exceeded their timeout.

        Called by the timeout sweeper background job (every 15 minutes).

        Args:
            now: Current time (UTC). Defaults to datetime.now(UTC).

        Returns:
            List of CloseSessionResult for closed sessions.
        """
        if now is None:
            now = datetime.now(UTC)

        db = self._db_session_factory()
        results: list[CloseSessionResult] = []

        try:
            from backend.models.person import ActivitySession

            # Find all open sessions
            open_sessions = db.execute(
                select(ActivitySession).where(ActivitySession.status == "open")
            ).scalars()

            for session in open_sessions:
                timeout_minutes = session.timeout_minutes
                if timeout_minutes is None:
                    continue

                timeout_delta = timedelta(minutes=timeout_minutes)
                if now - session.opened_at > timeout_delta:
                    # Session has timed out
                    duration_seconds = (now - session.opened_at).total_seconds()
                    duration_minutes = max(1, int(duration_seconds / 60))

                    session.closed_at = now
                    session.status = "closed"
                    session.duration_minutes = duration_minutes
                    session.metadata_json = {
                        **(session.metadata_json or {}),
                        "closed_via": "timeout",
                    }

                    db.add(session)

                    results.append(
                        CloseSessionResult(
                            session_id=session.id,
                            person_id=session.person_id,
                            activity_type=session.activity_type,
                            room_name=session.room_name,
                            opened_at=session.opened_at,
                            closed_at=now,
                            duration_minutes=duration_minutes,
                            status="closed",
                            closed_via="timeout",
                            source=session.source,
                            confidence=session.confidence,
                        )
                    )

                    logger.info(
                        "activity_session_timed_out",
                        person_id=session.person_id,
                        activity_type=session.activity_type,
                        session_id=session.id,
                        duration_minutes=duration_minutes,
                        timeout_minutes=timeout_minutes,
                    )

            if results:
                db.commit()
                logger.info(
                    "activity_session_timeout_batch",
                    count=len(results),
                    now=now.isoformat(),
                )

        except Exception:
            logger.exception("activity_session_timeout_error")
            db.rollback()
        finally:
            db.close()

        return results

    def get_open_sessions(self, person_id: str | None = None) -> list[dict]:
        """Get all open activity sessions.

        Args:
            person_id: Optional filter by person ID.

        Returns:
            List of session dicts with session details.
        """
        db = self._db_session_factory()
        try:
            from backend.models.person import ActivitySession

            stmt = select(ActivitySession).where(ActivitySession.status == "open")
            if person_id:
                stmt = stmt.where(ActivitySession.person_id == person_id)

            sessions = db.execute(stmt).scalars().all()

            return [
                {
                    "session_id": s.id,
                    "person_id": s.person_id,
                    "activity_type": s.activity_type,
                    "room_name": s.room_name,
                    "opened_at": s.opened_at,
                    "timeout_minutes": s.timeout_minutes,
                    "duration_minutes": s.duration_minutes,
                    "observation_id": s.observation_id,
                    "source": s.source,
                    "confidence": s.confidence,
                }
                for s in sessions
            ]
        finally:
            db.close()

    def get_sessions_for_day(self, person_id: str, date: str, tz_name: str = "UTC") -> list[dict]:
        """Get all closed sessions for a person on a specific date.

        Args:
            person_id: Household member ID.
            date: Date string in YYYY-MM-DD format.
            tz_name: Timezone for date interpretation (default UTC).

        Returns:
            List of closed session dicts sorted by opened_at descending.
        """

        from backend.models.person import ActivitySession

        db = self._db_session_factory()
        try:
            # Convert date to UTC range
            tz = ZoneInfo(tz_name)
            day_start = datetime(int(date[:4]), int(date[5:7]), int(date[8:]), tzinfo=tz)
            day_end = day_start + timedelta(days=1)

            day_start_utc = day_start.astimezone(UTC)
            day_end_utc = day_end.astimezone(UTC)

            stmt = (
                select(ActivitySession)
                .where(
                    and_(
                        ActivitySession.person_id == person_id,
                        ActivitySession.status == "closed",
                        or_(
                            and_(
                                ActivitySession.opened_at >= day_start_utc,
                                ActivitySession.opened_at < day_end_utc,
                            ),
                            and_(
                                ActivitySession.closed_at >= day_start_utc,
                                ActivitySession.closed_at < day_end_utc,
                            ),
                        ),
                    )
                )
                .order_by(ActivitySession.opened_at.desc())
            )

            sessions = db.execute(stmt).scalars().all()

            return [
                {
                    "session_id": s.id,
                    "person_id": s.person_id,
                    "activity_type": s.activity_type,
                    "room_name": s.room_name,
                    "opened_at": s.opened_at,
                    "closed_at": s.closed_at,
                    "duration_minutes": s.duration_minutes,
                    "status": s.status,
                    "closed_via": s.metadata_json.get("closed_via", "unknown")
                    if s.metadata_json
                    else "unknown",
                    "source": s.source,
                    "confidence": s.confidence,
                }
                for s in sessions
            ]
        finally:
            db.close()
