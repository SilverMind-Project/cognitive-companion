"""Scene trend context filter.

Detects patterns in a person's activity and location history over a
configurable time window. Uses PersonLocationService.presence_history()
for location-based trends (R2: SSOT).

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
        # (no extra fields needed: just set trend_type)
    }
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata
from backend.services.cts.metrics import cts_filter_degraded_total

logger = get_logger(__name__)

_FILTER_NAME = "scene_trend"

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

    async def evaluate(
        self,
        config: dict,
        sensor,
        now: datetime,
        db: Session | None = None,
        services: Any = None,
    ) -> bool:
        person_id: str | None = config.get("person_id")
        trend_type: str | None = config.get("trend_type")
        if not person_id or not trend_type:
            return False

        within_minutes: float = config.get("within_minutes", _DEFAULT_WINDOW_MINUTES)
        cutoff = now - timedelta(minutes=within_minutes)

        # R2: PersonLocationService is the SSOT for location-based trends.
        # unusual_activity only needs PersonActivity (db), so it can skip
        # the PersonLocationService requirement.
        needs_location = trend_type in ("prolonged_stay", "frequent_visits", "no_recent_activity")
        if needs_location and not (services and getattr(services, "person_location", None)):
            cts_filter_degraded_total.labels(filter=_FILTER_NAME).inc()
            logger.warning(
                "cts_filter_degraded_no_person_location",
                filter=_FILTER_NAME,
            )
            return False

        if trend_type == "prolonged_stay":
            return await self._check_prolonged_stay(person_id, config, cutoff, now, services)
        if trend_type == "frequent_visits":
            return await self._check_frequent_visits(person_id, config, cutoff, services)
        if trend_type == "unusual_activity":
            return self._check_unusual_activity(db, person_id, config, cutoff)
        if trend_type == "no_recent_activity":
            return await self._check_no_recent_activity(
                db, person_id, cutoff, services
            )

        return False

    # -- trend checkers -----------------------------------------------------

    async def _check_prolonged_stay(
        self,
        person_id: str,
        config: dict,
        cutoff: datetime,
        now: datetime,
        services: Any,
    ) -> bool:
        """Person has been in the same room continuously for > threshold (R2: PersonLocationService)."""
        threshold: int | None = config.get("threshold_minutes")
        if threshold is None:
            return False

        room_name: str | None = config.get("room_name")

        segments = await services.person_location.presence_history(
            person_id, since=cutoff, until=now
        )

        # Group by room and compute max stay duration.
        room_stays: dict[int, float] = {}
        for seg in segments:
            if seg.superseded_by is not None:
                continue
            if room_name and (seg.metadata.get("room_name", "") or "").lower() != room_name.lower():
                continue
            r = seg.room_id
            if r not in room_stays:
                room_stays[r] = 0.0
            end = seg.exited_at if seg.exited_at else now
            duration = (end - seg.entered_at).total_seconds() / 60
            if duration > room_stays[r]:
                room_stays[r] = duration

        return any(dur >= threshold for dur in room_stays.values())

    async def _check_frequent_visits(
        self,
        person_id: str,
        config: dict,
        cutoff: datetime,
        services: Any,
    ) -> bool:
        """Person visited a room >= visit_count times within the window (R2: PersonLocationService)."""
        min_visits: int | None = config.get("visit_count")
        if min_visits is None:
            return False

        room_name: str | None = config.get("room_name")

        segments = await services.person_location.presence_history(
            person_id, since=cutoff, until=cutoff + timedelta(days=1)
        )

        active = [s for s in segments if s.superseded_by is None]
        if room_name:
            active = [
                s for s in active
                if (s.metadata.get("room_name", "") or "").lower() == room_name.lower()
            ]
        return len(active) >= min_visits

    @staticmethod
    def _check_unusual_activity(
        db: Session | None,
        person_id: str,
        config: dict,
        cutoff: datetime,
    ) -> bool:
        """Person performed an activity >= activity_count times."""
        if db is None:
            return False
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

    async def _check_no_recent_activity(
        self,
        db: Session | None,
        person_id: str,
        cutoff: datetime,
        services: Any,
    ) -> bool:
        """Person has no location history or activity in the window (R2: PersonLocationService)."""
        # Check location via PersonLocationService.
        segments = await services.person_location.presence_history(
            person_id, since=cutoff, until=cutoff + timedelta(days=1)
        )
        has_location = any(
            s.superseded_by is None for s in segments
        )
        if has_location:
            return False

        # Check activity via DB (PersonActivity is not a legacy location table).
        if db is None:
            return True
        from backend.models.person import PersonActivity

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
