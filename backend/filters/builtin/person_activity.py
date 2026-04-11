"""Person activity context filter -- did person X do activity A recently?"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata


@FilterRegistry.register
class PersonActivityFilter(ContextFilter):
    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="person_activity",
            display_name="Person Activity",
            description="Check if a person performed a specific activity within a time window.",
            config_schema={
                "type": "object",
                "properties": {
                    "person_id": {"type": "string"},
                    "activity_type": {"type": "string"},
                    "within_minutes": {
                        "type": "number",
                        "default": 30,
                        "description": "Time window in minutes",
                    },
                },
                "required": ["person_id", "activity_type"],
            },
        )

    def evaluate(self, config: dict, sensor, now: datetime, db: Session | None = None) -> bool:
        if not db:
            return False
        from backend.models.person import PersonActivity

        person_id = config.get("person_id")
        activity_type = config.get("activity_type")
        within_minutes = config.get("within_minutes", 30)
        if not person_id or not activity_type:
            return False

        cutoff = now - timedelta(minutes=within_minutes)
        match = (
            db.query(PersonActivity)
            .filter(
                PersonActivity.person_id == person_id,
                PersonActivity.activity_type == activity_type,
                PersonActivity.detected_at >= cutoff,
            )
            .first()
        )
        return match is not None
