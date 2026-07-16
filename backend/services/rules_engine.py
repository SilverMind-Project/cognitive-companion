"""
Rules engine -- evaluates which rules match a given sensor event, checking
contexts (via FilterRegistry), dependencies, and rate limits.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.filters import FilterRegistry
from backend.models.event import EventLog
from backend.models.rule import Rule, RuleContext, RuleDependency
from backend.models.sensor import Sensor
from backend.steps.base import ServiceContainer

logger = get_logger(__name__)


class RulesEngine:
    """Determines which rules should fire for a given sensor event."""

    def __init__(self, services: ServiceContainer, tz_name: str | None = None) -> None:
        self._services = services
        self.tz = ZoneInfo(tz_name or settings.as_str("app.timezone"))

    # -- public API -----------------------------------------------------------

    async def get_matching_rules(
        self,
        sensor: Sensor,
        db: Session,
        trigger_type: str = "sensor_event",
        occupancy_minutes: float | None = None,
    ) -> list[Rule]:
        """Return enabled rules matching the sensor that pass all checks.

        Args:
            trigger_type: Only rules whose ``trigger_types`` JSON column
                contains this type are considered.
            occupancy_minutes: When ``trigger_type`` is ``"occupancy_duration"``,
                only rules whose ``occupancy_config.min_minutes`` threshold has
                been reached are included.
        """
        now = datetime.now(self.tz)
        query = db.query(Rule).filter(
            Rule.enabled.is_(True),
            Rule.filter_active(),
            Rule.trigger_types.contains([trigger_type]),
        )
        if trigger_type == "occupancy_duration":
            query = query.filter(Rule.primary_sensor_id == sensor.id)
        rules = query.all()

        if trigger_type == "occupancy_duration" and occupancy_minutes is not None:
            rules = [
                r
                for r in rules
                if (r.occupancy_config or {}).get("min_minutes", 40) <= occupancy_minutes
            ]

        matched: list[Rule] = []
        for rule in rules:
            if not await self._check_contexts(rule, sensor, now, db, "sensor"):
                logger.info("rule_skipped_context", rule=rule.name, sensor_id=sensor.id)
                continue
            if not self._check_dependencies(rule, db, now):
                logger.info("rule_skipped_dependency", rule=rule.name, sensor_id=sensor.id)
                continue
            if not self._check_rate_limits(rule, db, now):
                logger.info("rule_skipped_rate_limit", rule=rule.name, sensor_id=sensor.id)
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

    async def get_matching_rules_for_cron(
        self,
        rule: Rule,
        db: Session,
    ) -> bool:
        """Check whether *rule* should fire from a cron trigger.

        Evaluates contexts, dependencies, and rate limits against the current
        time. Returns True if all checks pass. Unlike sensor events, cron
        triggers have no sensor or room context.
        """
        now = datetime.now(self.tz)

        if not rule.enabled:
            return False

        if not await self._check_contexts(rule, None, now, db, "cron"):
            logger.info("rule_skipped_context", rule=rule.name, trigger="cron")
            return False
        if not self._check_dependencies(rule, db, now):
            logger.info("rule_skipped_dependency", rule=rule.name, trigger="cron")
            return False
        if not self._check_rate_limits(rule, db, now):
            logger.info("rule_skipped_rate_limit", rule=rule.name, trigger="cron")
            return False

        return True

    async def get_matching_rules_for_event(
        self,
        event: dict[str, Any],
        trigger_type: str,
        db: Session,
    ) -> list[Rule]:
        """Return enabled rules matching a dict-based event (e.g. dementia signals).

        Unlike :meth:`get_matching_rules`, this method does not require a SQLAlchemy
        Sensor row. It passes the event dict directly to context filters.
        Filters in :data:`_SENSOR_DEPENDENT_FILTERS` are skipped because they
        require a Sensor ORM object to evaluate.

        Args:
            event: Event dict shaped as ``{"kind": str, "payload": dict}``.
            trigger_type: The trigger type string to match against
                ``Rule.trigger_types`` (e.g. ``"dementia_signal"``).
            db: Active database session.
        """
        now = datetime.now(self.tz)
        rules = (
            db.query(Rule)
            .filter(
                Rule.enabled.is_(True),
                Rule.filter_active(),
                Rule.trigger_types.contains([trigger_type]),
            )
            .all()
        )

        matched: list[Rule] = []
        for rule in rules:
            if not await self._check_contexts(rule, event, now, db, "event"):
                logger.info(
                    "rule_skipped_context",
                    rule=rule.name,
                    trigger_type=trigger_type,
                )
                continue
            if not self._check_dependencies(rule, db, now):
                logger.info(
                    "rule_skipped_dependency",
                    rule=rule.name,
                    trigger_type=trigger_type,
                )
                continue
            if not self._check_rate_limits(rule, db, now):
                logger.info(
                    "rule_skipped_rate_limit",
                    rule=rule.name,
                    trigger_type=trigger_type,
                )
                continue
            matched.append(rule)

        logger.info(
            "rule_matching",
            trigger_type=trigger_type,
            total_rules=len(rules),
            matched=len(matched),
            matched_names=[r.name for r in matched],
        )
        return matched

    # -- context checking (via FilterRegistry) --------------------------------

    _SENSOR_DEPENDENT_FILTERS = frozenset({"room", "room_transition", "person_movement_memory"})

    # Warning event names selected by trigger_label so existing log-based
    # dashboards keep working; the sensor path never actually skips (subject
    # is always a real Sensor there) but gets a name for completeness.
    _SKIP_WARNING_EVENT = {
        "sensor": "sensor_context_skipped_sensor_dependent",
        "cron": "cron_context_skipped_sensor_dependent",
        "event": "event_context_skipped_sensor_dependent",
    }

    async def _check_contexts(
        self,
        rule: Rule,
        subject: Sensor | dict[str, Any] | None,
        now: datetime,
        db: Session | None,
        trigger_label: str,
    ) -> bool:
        """Contexts act as filters.

        Within each ``context_type`` group, at least one must match (OR).
        Across groups, all must pass (AND). Sensor-dependent filter types
        are skipped (with a warning) when *subject* is not a real
        :class:`Sensor` row -- true for cron triggers (no subject) and
        dict-based event triggers (dementia signals etc.).
        """
        if not rule.contexts:
            return True

        by_type: dict[str, list[RuleContext]] = {}
        for ctx in rule.contexts:
            by_type.setdefault(ctx.context_type, []).append(ctx)

        subject_is_sensor = isinstance(subject, Sensor)

        for ctx_type, contexts in by_type.items():
            if ctx_type in self._SENSOR_DEPENDENT_FILTERS and not subject_is_sensor:
                logger.warning(
                    self._SKIP_WARNING_EVENT[trigger_label],
                    rule=rule.name,
                    context_type=ctx_type,
                )
                continue
            if not await self._any_context_matches(contexts, subject, now, db):
                return False
        return True

    async def _any_context_matches(
        self,
        contexts: list[RuleContext],
        subject: Sensor | dict[str, Any] | None,
        now: datetime,
        db: Session | None,
    ) -> bool:
        for ctx in contexts:
            if await self._matches_context(ctx, subject, now, db):
                return True
        return False

    async def _matches_context(
        self,
        ctx: RuleContext,
        subject: Sensor | dict[str, Any] | None,
        now: datetime,
        db: Session | None = None,
    ) -> bool:
        """Delegate context evaluation to the FilterRegistry.

        When ``ctx.negate`` is True the filter result is inverted, enabling
        rules like "NOT in Kitchen" or "NOT during 09:00-17:00".

        Filter evaluate methods may be sync or async; async results are
        awaited on the caller's running loop (never bridged with
        ``run_until_complete``).
        """
        filter_instance = FilterRegistry.get(ctx.context_type)
        if filter_instance:
            result = filter_instance.evaluate(
                ctx.config_json or {}, subject, now, db, self._services
            )
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, bool):
                raise TypeError(
                    f"filter {ctx.context_type} returned {type(result).__name__}, expected bool"
                )
            return (not result) if ctx.negate else result
        logger.warning("unknown_context_type", context_type=ctx.context_type)
        return True  # unknown type = don't filter

    # -- dependency checking --------------------------------------------------

    def _check_dependencies(self, rule: Rule, db: Session, now: datetime) -> bool:
        """All dependencies must pass (AND logic)."""
        for dep in rule.dependencies:
            if not self._check_single_dependency(dep, db, now):
                logger.info(
                    "dependency_failed",
                    rule=rule.name,
                    parent_rule_id=dep.parent_rule_id,
                    require_success=dep.require_success,
                    lookback_minutes=dep.lookback_minutes,
                )
                return False
        return True

    def _check_single_dependency(self, dep: RuleDependency, db: Session, now: datetime) -> bool:
        now_utc = now.astimezone(UTC)
        cutoff = now_utc - timedelta(minutes=dep.lookback_minutes)
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
        """Check cool-off period and daily trigger limit.

        Both checks compare against UTC timestamps stored in the database.
        The cool-off window is relative (minutes elapsed) so UTC conversion is
        straightforward.  The daily limit window starts at **local midnight**
        in the configured timezone: "today" means the current calendar day as
        seen by the operator, not the UTC day boundary.
        """
        if rule.cool_off_minutes > 0:
            now_utc = now.astimezone(UTC)
            cutoff = now_utc - timedelta(minutes=rule.cool_off_minutes)
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
                logger.info(
                    "cooloff_active",
                    rule=rule.name,
                    cool_off_minutes=rule.cool_off_minutes,
                    cutoff=cutoff,
                )
                return False

        if rule.max_daily_triggers > 0:
            # "Today" = the calendar day in the operator's configured timezone.
            # Midnight in local time is converted to UTC for the query.
            local_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            midnight_utc = local_midnight.astimezone(UTC)
            count = (
                db.query(func.count(EventLog.id))
                .filter(
                    EventLog.rule_id == rule.id,
                    EventLog.status == "completed",
                    EventLog.timestamp >= midnight_utc,
                )
                .scalar()
            )
            if count >= rule.max_daily_triggers:
                logger.info(
                    "daily_limit_reached", rule=rule.name, count=count, max=rule.max_daily_triggers
                )
                return False

        return True
