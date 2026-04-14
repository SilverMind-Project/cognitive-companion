"""Room transition context filter.

Passes when a person has completed a semantically-tagged room transition
(derived from camera topology) within the configured time window.

Typical use case: "alert me when Grandma *enters* the Kitchen in the last 2 minutes."

Config schema
-------------
::

    {
        "person_id": "abc123",          # required
        "semantic": "entering",         # optional: entering | exiting |
                                        #   approaching_exit | entering_depth
        "to_room_name": "Kitchen",      # optional: destination room (case-insensitive)
        "from_room_name": "Hallway",    # optional: origin room (case-insensitive)
        "within_minutes": 5             # default: 5
    }

All optional fields are ANDed: the filter passes only when every supplied
constraint matches at least one history row in the time window.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata
from backend.services.camera_topology import (
    SEMANTIC_APPROACHING_EXIT,
    SEMANTIC_ENTERING,
    SEMANTIC_ENTERING_DEPTH,
    SEMANTIC_EXITING,
    SEMANTIC_STATIONARY,
)

_VALID_SEMANTICS = (
    SEMANTIC_ENTERING,
    SEMANTIC_EXITING,
    SEMANTIC_APPROACHING_EXIT,
    SEMANTIC_ENTERING_DEPTH,
    SEMANTIC_STATIONARY,
)

_DEFAULT_WINDOW_MINUTES = 5


@FilterRegistry.register
class RoomTransitionFilter(ContextFilter):
    """Passes when the configured person has a topology-derived room-transition
    entry in ``PersonLocationHistory`` within the requested time window."""

    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="room_transition",
            display_name="Room Transition",
            description=(
                "Check if a person entered, exited, or passed through a room "
                "within a time window (requires camera topology to be configured)."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": "Person ID to check",
                    },
                    "semantic": {
                        "type": "string",
                        "enum": list(_VALID_SEMANTICS),
                        "description": "Semantic direction (entering, exiting, …). Omit to match any.",
                    },
                    "to_room_name": {
                        "type": "string",
                        "description": "Destination room name (case-insensitive). Omit to match any.",
                    },
                    "from_room_name": {
                        "type": "string",
                        "description": "Origin room name (case-insensitive). Omit to match any.",
                    },
                    "within_minutes": {
                        "type": "number",
                        "minimum": 0.1,
                        "default": _DEFAULT_WINDOW_MINUTES,
                        "description": "Look-back window in minutes.",
                    },
                },
                "required": ["person_id"],
            },
        )

    def evaluate(self, config: dict, sensor, now: datetime, db: Session | None = None) -> bool:
        if not db:
            return False

        from backend.models.person import PersonLocationHistory

        person_id: str | None = config.get("person_id")
        if not person_id:
            return False

        within_minutes: float = config.get("within_minutes", _DEFAULT_WINDOW_MINUTES)
        cutoff = now - timedelta(minutes=within_minutes)

        query = db.query(PersonLocationHistory).filter(
            PersonLocationHistory.person_id == person_id,
            PersonLocationHistory.entered_at >= cutoff,
            # Only rows produced by topology inference carry a direction_semantic.
            PersonLocationHistory.direction_semantic.isnot(None),
        )

        semantic: str | None = config.get("semantic")
        if semantic:
            query = query.filter(PersonLocationHistory.direction_semantic == semantic)

        to_room: str | None = config.get("to_room_name")
        if to_room:
            # room_name on PersonLocationHistory is the *destination* room.
            query = query.filter(PersonLocationHistory.room_name.ilike(to_room))

        from_room: str | None = config.get("from_room_name")
        if from_room:
            query = query.filter(PersonLocationHistory.from_room_name.ilike(from_room))

        return query.first() is not None
