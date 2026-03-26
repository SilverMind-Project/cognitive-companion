"""Day of week context filter."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata


@FilterRegistry.register
class DayOfWeekFilter(ContextFilter):

    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="day_of_week",
            display_name="Day of Week",
            description="Filter rules by day of the week (0=Monday, 6=Sunday).",
            config_schema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 0, "maximum": 6},
                        "description": "Days of week (0=Monday, 6=Sunday)",
                    },
                },
            },
        )

    def evaluate(self, config: dict, sensor, now: datetime, db: Session | None = None) -> bool:
        days = config.get("days", [])
        return now.weekday() in days
