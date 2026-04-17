"""Scene trend context filter.

Detects patterns in a person's activity and location history over a
configurable time window. Useful for rules like "alert if Grandma has
been stationary in the bathroom for 30+ minutes" or "flag if someone
has had 5+ bathroom visits in the last hour."

Config schema
-------------
::

    {
        "person_id": "abc123",          # required

        # Trend type (required):
        "trend_type": "prolonged_stay", # required: prolonged_stay |
                                        #   frequent_visits |
                                        #   unusual_activity |
                                        #   no_recent_activity

        # Shared optional fields:
        "room_name": "Bathroom",        # optional: filter to a specific room
        "within_minutes": 60,           # optional: look-back window (default: 60)

        # prolonged_stay: person has been in the same room for > threshold
        "threshold_minutes": 30,        # required for prolonged_stay

        # frequent_visits: person visited a room > N times
        "visit_count": 5,               # required for frequent_visits

        # unusual_activity: person did an activity > N times
        "activity_type": "bathroom",    # required for unusual_activity
        "activity_count": 5,            # required for unusual_activity

        # no_recent_activity: person hasn't been seen in the window
        # (no extra fields needed — just set trend_type)
    }
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata

_VALID_TREND_TYPES = (
    "prolonged_stay",
    "frequent_visits",
    "unusual_activity",
    "no_recent_activity",
)

_DEFAULT_WINDOW_MINUTES = 60


@FilterRegistry.register
class SceneTrendFilter(ContextFilter):
    """Passes when the configured person exhibits a detected trend."""

    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="scene_trend",
            display_name="Scene Trend",
            description=(
                "Detect patterns in a person's activity and location "
                "history: prolonged stays, frequent visits, unusual "
                "activity counts, or no recent activity."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": "Person ID to check",
                    },
                    "trend_type": {
                        "type": "string",
                        "enum": list(_VALID_TREND_TYPES),
                        "description": "Type of trend to detect",
                    },
                    "room_name": {
                        "type": "string",
                        "description": "Filter to a specific room (case-insensitive). Optional.",
                    },
                    "within_minutes": {
                        "type": "number",
                        "minimum": 0.1,
                        "default": _DEFAULT_WINDOW_MINUTES,
                        "description": "Look-back window in minutes.",
                    },
                    "threshold_minutes": {
                        "type": "number",
                        "minimum": 1,
                        "description": "Duration threshold in minutes (prolonged_stay).",
                    },
                    "visit_count": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Minimum visit count (frequent_visits).",
                    },
                    "activity_type": {
                        "type": "string",
                        "description": "Activity type to count (unusual_activity).",
                    },
                    "activity_count": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Minimum activity count (unusual_activity).",
                    },
                },
                "required": ["person_id", "trend_type"],
            },
        )

    def evaluate(self, config: dict, sensor, now: datetime, db: Session | None = None) -> bool:
        if not db:
            return False

        person_id: str | None = config.get("person_id")
        trend_type: str | None = config.get("trend_type")
        if not person_id or not trend_type:
            return False

        within_minutes: float = config.get("within_minutes", _DEFAULT_WINDOW_MINUTES)
        cutoff = now - timedelta(minutes=within_minutes)

        if trend_type == "prolonged_stay":
            return self._check_prolonged_stay(db, person_id, config, cutoff, now)
        if trend_type == "frequent_visits":
            return self._check_frequent_visits(db, person_id, config, cutoff)
        if trend_type == "unusual_activity":
            return self._check_unusual_activity(db, person_id, config, cutoff)
        if trend_type == "no_recent_activity":
            return self._check_no_recent_activity(db, person_id, cutoff)

        return False

    # -- trend checkers -----------------------------------------------------

    def _check_prolonged_stay(
        self, db: Session, person_id: str, config: dict, cutoff: datetime, now: datetime
    ) -> bool:
        """Person has been in the same room continuously for > threshold."""
        from backend.models.person import PersonLocationHistory

        threshold: int | None = config.get("threshold_minutes")
        if threshold is None:
            return False

        room_name: str | None = config.get("room_name")

        # Find all location entries for the person within the window.
        stmt = (
            select(PersonLocationHistory)
            .where(
                PersonLocationHistory.person_id == person_id,
                PersonLocationHistory.entered_at <= cutoff,
            )
        )
        if room_name:
            stmt = stmt.where(PersonLocationHistory.room_name.ilike(room_name))

        entries = db.execute(stmt).scalars().all()

        # Group by room and compute max stay duration.
        room_stays: dict[str, float] = {}
        for entry in entries:
            room = entry.room_name or "unknown"
            if room not in room_stays:
                room_stays[room] = 0.0
            # Duration is from entered_at to exited_at (or now if still there).
            end = entry.exited_at if entry.exited_at else now
            duration = (end - entry.entered_at).total_seconds() / 60
            if duration > room_stays[room]:
                room_stays[room] = duration

        return any(dur >= threshold for dur in room_stays.values())

    def _check_frequent_visits(
        self, db: Session, person_id: str, config: dict, cutoff: datetime
    ) -> bool:
        """Person visited a room >= visit_count times within the window."""
        min_visits: int | None = config.get("visit_count")
        if min_visits is None:
            return False

        room_name: str | None = config.get("room_name")

        from backend.models.person import PersonLocationHistory

        stmt = (
            select(func.count(PersonLocationHistory.id))
            .where(
                PersonLocationHistory.person_id == person_id,
                PersonLocationHistory.entered_at >= cutoff,
            )
        )
        if room_name:
            stmt = stmt.where(PersonLocationHistory.room_name.ilike(room_name))

        count = db.execute(stmt).scalar()
        return (count or 0) >= min_visits

    def _check_unusual_activity(
        self, db: Session, person_id: str, config: dict, cutoff: datetime
    ) -> bool:
        """Person performed an activity >= activity_count times."""
        activity_type: str | None = config.get("activity_type")
        min_count: int | None = config.get("activity_count")
        if not activity_type or min_count is None:
            return False

        from backend.models.person import PersonActivity

        count = (
            db.query(func.count(PersonActivity.id))
            .filter(
                PersonActivity.person_id == person_id,
                PersonActivity.activity_type == activity_type,
                PersonActivity.detected_at >= cutoff,
            )
            .scalar()
        )
        return count >= min_count

    def _check_no_recent_activity(
        self, db: Session, person_id: str, cutoff: datetime
    ) -> bool:
        """Person has no location history or activity in the window."""
        from backend.models.person import PersonActivity, PersonLocationHistory

        has_location = (
            db.query(PersonLocationHistory.id)
            .filter(
                PersonLocationHistory.person_id == person_id,
                PersonLocationHistory.entered_at >= cutoff,
            )
            .limit(1)
            .first()
        )
        if has_location:
            return False

        has_activity = (
            db.query(PersonActivity.id)
            .filter(
                PersonActivity.person_id == person_id,
                PersonActivity.detected_at >= cutoff,
            )
            .limit(1)
            .first()
        )
        return has_activity is None
