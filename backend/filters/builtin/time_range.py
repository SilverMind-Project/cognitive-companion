"""Time range context filter -- match rule to time windows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata


@FilterRegistry.register
class TimeRangeFilter(ContextFilter):
    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="time_range",
            display_name="Time Range",
            description="Filter rules by time of day (supports overnight ranges).",
            config_schema={
                "type": "object",
                "properties": {
                    "start_time": {
                        "type": "string",
                        "description": "Start time in HH:MM format",
                        "default": "00:00",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time in HH:MM format",
                        "default": "23:59",
                    },
                },
            },
        )

    def evaluate(self, config: dict, sensor, now: datetime, db: Session | None = None) -> bool:
        start_str = config.get("start_time", "00:00")
        end_str = config.get("end_time", "23:59")
        current = now.strftime("%H:%M")
        if start_str <= end_str:
            return start_str <= current <= end_str
        # Overnight range (e.g., 22:00 - 06:00)
        return current >= start_str or current <= end_str
