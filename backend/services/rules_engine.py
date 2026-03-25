"""
Rules engine – evaluates which rules match a given sensor event, checking
contexts, dependencies, and rate limits.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.models.event import EventLog
from backend.models.person import PersonActivity, PersonLocationState
from backend.models.rule import Rule, RuleContext, RuleDependency
from backend.models.sensor import Sensor

logger = get_logger(__name__)


class RulesEngine:
    """Determines which rules should fire for a given sensor event."""

    def __init__(self, tz_name: str | None = None) -> None:
        self.tz = ZoneInfo(tz_name or settings.get("app.timezone", "America/New_York"))

    # -- public API -----------------------------------------------------------

    def get_matching_rules(
        self,
        sensor: Sensor,
        db: Session,
    ) -> list[Rule]:
        """
        Return all enabled rules that match the sensor's room and the current
        time, pass dependency checks, and are within rate limits.
        """
        now = datetime.now(self.tz)
        rules = db.query(Rule).filter(Rule.enabled.is_(True)).all()

        matched: list[Rule] = []
        for rule in rules:
            if not self._check_contexts(rule, sensor, now, db):
                continue
            if not self._check_dependencies(rule, db, now):
                continue
            if not self._check_rate_limits(rule, db, now):
                continue
            matched.append(rule)

        logger.info(
            "rule_matching",
            sensor_id=sensor.id,
            room=sensor.room.name if sensor.room else None,
            total_rules=len(rules),
            matched=len(matched),
            matched_names=[r.name for r in matched],
        )
        return matched

    # -- context checking -----------------------------------------------------

    def _check_contexts(
        self, rule: Rule, sensor: Sensor, now: datetime, db: Session | None = None
    ) -> bool:
        """Contexts act as filters.

        Within each ``context_type`` group, at least one must match (OR).
        Across groups, all must pass (AND).
        """
        if not rule.contexts:
            return True  # no contexts = applies everywhere

        by_type: dict[str, list[RuleContext]] = {}
        for ctx in rule.contexts:
            by_type.setdefault(ctx.context_type, []).append(ctx)

        for ctx_type, contexts in by_type.items():
            if not any(self._matches_context(ctx, sensor, now, db) for ctx in contexts):
                return False
        return True

    def _matches_context(
        self, ctx: RuleContext, sensor: Sensor, now: datetime, db: Session | None = None
    ) -> bool:
        cfg = ctx.config_json or {}

        if ctx.context_type == "room":
            room_name = cfg.get("room_name", "")
            room_id = cfg.get("room_id")
            if room_id and sensor.room_id:
                return sensor.room_id == room_id
            if room_name and sensor.room:
                return sensor.room.name.lower() == room_name.lower()
            return False

        if ctx.context_type == "time_range":
            start_str = cfg.get("start_time", "00:00")
            end_str = cfg.get("end_time", "23:59")
            current = now.strftime("%H:%M")
            if start_str <= end_str:
                return start_str <= current <= end_str
            # Handles overnight ranges (e.g., 22:00 - 06:00)
            return current >= start_str or current <= end_str

        if ctx.context_type == "day_of_week":
            days = cfg.get("days", [])
            return now.weekday() in days

        if ctx.context_type == "person_presence" and db:
            # Is person X currently in room Y?
            person_id = cfg.get("person_id")
            room_name = cfg.get("room_name")
            if not person_id:
                return False
            loc = (
                db.query(PersonLocationState)
                .filter(PersonLocationState.person_id == person_id)
                .first()
            )
            if not loc:
                return False
            if room_name:
                return (loc.current_room_name or "").lower() == room_name.lower()
            # If no room specified, just check that person is tracked
            return loc.status == "home"

        if ctx.context_type == "person_activity" and db:
            # Did person X do activity A in the last N minutes?
            person_id = cfg.get("person_id")
            activity_type = cfg.get("activity_type")
            within_minutes = cfg.get("within_minutes", 30)
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

        logger.warning("unknown_context_type", context_type=ctx.context_type)
        return True  # unknown type = don't filter

    # -- dependency checking --------------------------------------------------

    def _check_dependencies(self, rule: Rule, db: Session, now: datetime) -> bool:
        """All dependencies must pass (AND logic)."""
        for dep in rule.dependencies:
            if not self._check_single_dependency(dep, db, now):
                logger.debug(
                    "dependency_failed",
                    rule=rule.name,
                    parent_rule_id=dep.parent_rule_id,
                    require_success=dep.require_success,
                )
                return False
        return True

    def _check_single_dependency(self, dep: RuleDependency, db: Session, now: datetime) -> bool:
        cutoff = now - timedelta(minutes=dep.lookback_minutes)
        recent_success = (
            db.query(EventLog)
            .filter(
                EventLog.rule_id == dep.parent_rule_id,
                EventLog.status == "completed",
                EventLog.timestamp >= cutoff,
            )
            .first()
        )
        if dep.require_success:
            return recent_success is not None
        else:
            return recent_success is None

    # -- rate limit checking --------------------------------------------------

    def _check_rate_limits(self, rule: Rule, db: Session, now: datetime) -> bool:
        """Check cool-off period and daily trigger limit."""
        # Cool-off check
        if rule.cool_off_minutes > 0:
            cutoff = now - timedelta(minutes=rule.cool_off_minutes)
            recent = (
                db.query(EventLog)
                .filter(
                    EventLog.rule_id == rule.id,
                    EventLog.status == "completed",
                    EventLog.timestamp >= cutoff,
                )
                .first()
            )
            if recent:
                logger.debug("cooloff_active", rule=rule.name)
                return False

        # Daily limit check
        if rule.max_daily_triggers > 0:
            # Count completions since midnight in configured timezone
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            count = (
                db.query(func.count(EventLog.id))
                .filter(
                    EventLog.rule_id == rule.id,
                    EventLog.status == "completed",
                    EventLog.timestamp >= midnight,
                )
                .scalar()
            )
            if count >= rule.max_daily_triggers:
                logger.debug("daily_limit_reached", rule=rule.name, count=count)
                return False

        return True
