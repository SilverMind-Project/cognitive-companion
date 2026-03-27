"""
Rules engine -- evaluates which rules match a given sensor event, checking
contexts (via FilterRegistry), dependencies, and rate limits.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.filters import FilterRegistry
from backend.models.event import EventLog
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
        trigger_type: str = "sensor_event",
        occupancy_minutes: float | None = None,
    ) -> list[Rule]:
        """Return enabled rules matching the sensor that pass all checks.

        Args:
            trigger_type: Only rules with this trigger_type are considered.
            occupancy_minutes: When ``trigger_type`` is ``"occupancy_duration"``,
                only rules whose ``occupancy_config.min_minutes`` threshold has
                been reached are included.
        """
        now = datetime.now(self.tz)
        query = db.query(Rule).filter(
            Rule.enabled.is_(True),
            Rule.trigger_type == trigger_type,
        )
        if trigger_type == "occupancy_duration":
            query = query.filter(Rule.primary_sensor_id == sensor.id)
        rules = query.all()

        if trigger_type == "occupancy_duration" and occupancy_minutes is not None:
            rules = [
                r for r in rules
                if (r.occupancy_config or {}).get("min_minutes", 40) <= occupancy_minutes
            ]

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
            trigger_type=trigger_type,
            room=sensor.room.name if sensor.room else None,
            total_rules=len(rules),
            matched=len(matched),
            matched_names=[r.name for r in matched],
        )
        return matched

    # -- context checking (via FilterRegistry) --------------------------------

    def _check_contexts(
        self, rule: Rule, sensor: Sensor, now: datetime, db: Session | None = None
    ) -> bool:
        """Contexts act as filters.

        Within each ``context_type`` group, at least one must match (OR).
        Across groups, all must pass (AND).
        """
        if not rule.contexts:
            return True

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
        """Delegate context evaluation to the FilterRegistry.

        When ``ctx.negate`` is True the filter result is inverted, enabling
        rules like "NOT in Kitchen" or "NOT during 09:00–17:00".
        """
        filter_instance = FilterRegistry.get(ctx.context_type)
        if filter_instance:
            result = filter_instance.evaluate(ctx.config_json or {}, sensor, now, db)
            return (not result) if ctx.negate else result
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

        if rule.max_daily_triggers > 0:
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
