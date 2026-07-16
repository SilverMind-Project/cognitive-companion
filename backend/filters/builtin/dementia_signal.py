"""Dementia signal context filter -- match on dementia signal events.

Rules can use this filter to fire when a dementia signal of a specific
type, severity, or person appears.  Supports cooldown to suppress
consecutive matches.

Config schema::

    {
        "kinds": ["pacing", "sundowning", "bathroom_dwell_anomaly"],
        "person_ids": ["grandma", "dad"],
        "min_severity": 0.7,
        "time_of_day": {"start": "20:00", "end": "22:00"},
        "cooldown_minutes": 30
    }

All config keys are optional.  An empty config matches any signal.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata
from backend.services.cts.signal_config import ALL_SIGNAL_KINDS


@FilterRegistry.register
class DementiaSignalFilter(ContextFilter):
    """Match dementia signal events against configurable criteria.

    This filter is evaluated when the rule pipeline processes an event
    with ``kind == "dementia_signal"``.  It checks the signal type,
    person ID, severity, time of day, and cooldown state.
    """

    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="dementia_signal",
            display_name="Dementia Signal",
            description="Match on dementia signal type, severity, person, and time window.",
            config_schema={
                "type": "object",
                "properties": {
                    "kinds": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(ALL_SIGNAL_KINDS)},
                        "description": "Signal types to match (empty = any).",
                    },
                    "person_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Person IDs to match (empty = any).",
                    },
                    "min_severity": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "default": 0.0,
                        "description": "Minimum severity threshold (0.0-1.0).",
                    },
                    "time_of_day": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string", "pattern": "^([01]\\d|2[0-3]):[0-5]\\d$"},
                            "end": {"type": "string", "pattern": "^([01]\\d|2[0-3]):[0-5]\\d$"},
                        },
                        "description": "Time window in HH:MM format (local TZ).",
                    },
                    "cooldown_minutes": {
                        "type": "number",
                        "default": 0,
                        "description": "Suppress consecutive matches within N minutes per (rule_id, person_id, kind).",
                    },
                },
            },
        )

    def evaluate(
        self,
        config: dict,
        sensor,
        now: datetime,
        db: Session | None = None,
        services: Any = None,
    ) -> bool:
        """Evaluate whether a dementia signal event matches this filter.

        Args:
            config: filter configuration from the rule.
            sensor: the event dict with ``kind`` and ``payload`` keys.
            now: current time.
            db: optional database session (used for cooldown check).

        Returns:
            True if the signal matches all configured criteria.
        """
        if not isinstance(sensor, dict):
            return False

        # The event must be a dementia_signal.
        if sensor.get("kind") != "dementia_signal":
            return False

        payload = sensor.get("payload", {})
        if not payload:
            return False

        # Check signal kinds.
        kinds = config.get("kinds")
        if kinds:
            signal_kind = payload.get("signal_kind", "").lower()
            if signal_kind not in [k.lower() for k in kinds]:
                return False

        # Check person IDs.
        person_ids = config.get("person_ids")
        if person_ids:
            person_id = payload.get("person_id", "")
            if person_id not in person_ids:
                return False

        # Check severity (min_severity is 0.0-1.0 mapped from severity labels).
        severity_rank = self._severity_rank(payload.get("severity", "info"))
        min_severity = config.get("min_severity", 0.0)
        if severity_rank < min_severity:
            return False

        # Check time of day.
        time_config = config.get("time_of_day")
        if time_config and not self._time_of_day_matches(
            time_config, payload.get("window_end", "")
        ):
            return False

        # Check cooldown.
        cooldown = config.get("cooldown_minutes", 0)
        if cooldown <= 0 or db is None:
            return True

        return not self._is_cooldown_active(
            config=config,
            payload=payload,
            now=now,
            db=db,
            cooldown_minutes=cooldown,
        )

    @staticmethod
    def _severity_rank(severity: str) -> float:
        """Map severity label to a numeric rank for comparison."""
        return {"info": 0.33, "warning": 0.66, "emergency": 1.0}.get(severity.lower(), 0.0)

    @staticmethod
    def _time_of_day_matches(time_config: dict, window_end: str | datetime) -> bool:
        """Check if window_end falls within the configured time window."""
        start_str = time_config.get("start", "00:00")
        end_str = time_config.get("end", "23:59")

        try:
            dt = datetime.fromisoformat(window_end) if isinstance(window_end, str) else window_end

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)

            event_time = dt.time()
            start = datetime.strptime(start_str, "%H:%M").time()
            end = datetime.strptime(end_str, "%H:%M").time()

            if start <= end:
                return start <= event_time <= end
            else:
                # Crosses midnight.
                return event_time >= start or event_time <= end
        except ValueError, TypeError:
            return False

    @staticmethod
    def _is_cooldown_active(
        config: dict,
        payload: dict,
        now: datetime,
        db: Session,
        cooldown_minutes: int,
    ) -> bool:
        """Check if a recent matching signal exists within the cooldown window."""
        from backend.models.cts_signal import DementiaSignal

        person_id = payload.get("person_id", "")
        signal_kind = payload.get("signal_kind", "")

        cutoff = now - timedelta(minutes=cooldown_minutes)

        # Check if a matching signal was acknowledged within the cooldown window.
        recent = (
            db.query(DementiaSignal)
            .filter(
                DementiaSignal.person_id == person_id,
                DementiaSignal.signal_type == signal_kind,
                DementiaSignal.acknowledged_at >= cutoff,
            )
            .first()
        )
        return recent is not None
