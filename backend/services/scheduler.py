"""APScheduler setup: periodic rule execution, workflow resume, maintenance.

The core of this module is the :class:`Scheduler` class, which owns the
``AsyncIOScheduler``, the DB session factory, and a reference to the pipeline
executor. Everything else (``setup_scheduler``, ``reload_scheduled_rules``,
``execute_periodic_rule``, ``_resume_workflow_callback``) is a thin
module-level facade preserved for backward compatibility with existing call
sites (``backend.main``, ``backend.mcp.server``).

Tests should prefer constructing :class:`Scheduler` directly over touching
the module facade: it takes an ``event_aggregator``, a ``db_session_factory``,
and an optional ``pipeline_executor``, and exposes ``apscheduler`` (the
underlying ``AsyncIOScheduler``) plus every callback as a regular method.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger as ApschedulerCronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.models.cron_trigger import CronTrigger, RuleCronTrigger
from backend.models.rule import Rule
from backend.services.event_aggregator import EventAggregator

logger = get_logger(__name__)


def _app_timezone() -> ZoneInfo:
    """Return the application timezone from settings.

    Cron expressions entered by operators are always interpreted in this
    timezone so that a rule scheduled for "08:00" fires at 08:00 local time
    regardless of the server's system timezone.  APScheduler handles DST
    transitions automatically when a ``ZoneInfo`` object is supplied.
    """
    return ZoneInfo(settings.as_str("app.timezone"))


class Scheduler:
    """Owns an ``AsyncIOScheduler`` plus the context needed to run jobs.

    Construct one per application instance. The class is test-friendly:
    everything it needs is passed in, and every callback is a bound method
    rather than a module-level function reading globals.
    """

    def __init__(
        self,
        event_aggregator: EventAggregator,
        db_session_factory: Callable[[], Session],
        pipeline_executor: Any = None,
        *,
        rules_engine: Any = None,
        apscheduler: AsyncIOScheduler | None = None,
    ) -> None:
        self._event_aggregator = event_aggregator
        self._db_session_factory = db_session_factory
        self._pipeline_executor = pipeline_executor
        self._rules_engine = rules_engine
        self._scheduler = apscheduler or AsyncIOScheduler()

    # -- public API ---------------------------------------------------------

    @property
    def apscheduler(self) -> AsyncIOScheduler:
        """The underlying ``AsyncIOScheduler`` (for ``add_job`` etc.)."""
        return self._scheduler

    @property
    def pipeline_executor(self) -> Any:
        return self._pipeline_executor

    @pipeline_executor.setter
    def pipeline_executor(self, executor: Any) -> None:
        self._pipeline_executor = executor

    def configure(self) -> AsyncIOScheduler:
        """Register maintenance jobs, rule jobs, and pending resume jobs."""
        self._scheduler.add_job(
            self._event_aggregator.cleanup_expired_media,
            trigger=IntervalTrigger(minutes=5),
            id="cleanup_expired_media",
            name="Cleanup expired media objects",
            replace_existing=True,
        )
        logger.info("scheduler_maintenance_job_added", job="cleanup_expired_media")

        self._load_rule_jobs()
        self._schedule_pending_resumes()

        logger.info("scheduler_setup_complete")
        return self._scheduler

    def reload_rules(self) -> None:
        """Remove all rule-based jobs and re-add them from the database."""
        for job in self._scheduler.get_jobs():
            if job.id.startswith("cron_"):
                self._scheduler.remove_job(job.id)
                logger.debug("rule_job_removed", job_id=job.id)

        self._load_rule_jobs()
        logger.info("scheduled_rules_reloaded")

    def schedule_workflow_resume(self, execution_id: int, resume_at: datetime) -> None:
        """Register a one-shot resume job for a waiting workflow execution."""
        job_id = f"resume_{execution_id}"
        self._scheduler.add_job(
            self.resume_workflow,
            trigger=DateTrigger(run_date=resume_at),
            args=[execution_id],
            id=job_id,
            name=f"Resume workflow #{execution_id}",
            replace_existing=True,
        )
        logger.info(
            "workflow_resume_scheduled",
            execution_id=execution_id,
            resume_at=resume_at.isoformat(),
        )

    # -- callbacks ----------------------------------------------------------

    async def execute_periodic_rule(self, cron_trigger_id: int) -> None:
        """Execute all rules linked to a cron trigger, filtered through RulesEngine.

        One job is scheduled per CronTrigger. When it fires, all rules linked
        via rule_cron_triggers are evaluated for contexts, dependencies, and
        rate limits before execution.
        """
        if not self._pipeline_executor:
            logger.warning("pipeline_executor_not_set", cron_trigger_id=cron_trigger_id)
            return

        from backend.services.pipeline_executor import TriggerContext

        db: Session = self._db_session_factory()
        try:
            ct = db.get(CronTrigger, cron_trigger_id)
            if ct is None:
                logger.warning("cron_trigger_not_found", cron_trigger_id=cron_trigger_id)
                return

            if not ct.enabled:
                logger.debug("cron_trigger_disabled", cron_trigger_id=cron_trigger_id, name=ct.name)
                return

            # Find all enabled rules linked to this cron trigger
            rule_ids = [
                row[0]
                for row in db.query(RuleCronTrigger.rule_id)
                .filter(RuleCronTrigger.cron_trigger_id == cron_trigger_id)
                .all()
            ]
            rules = db.query(Rule).filter(Rule.id.in_(rule_ids), Rule.enabled.is_(True)).all()

            logger.info(
                "cron_trigger_fired",
                cron_trigger_id=cron_trigger_id,
                cron_trigger_name=ct.name,
                expression=ct.expression,
                linked_rules=len(rules),
            )

            for rule in rules:
                if (
                    self._rules_engine is not None
                    and not self._rules_engine.get_matching_rules_for_cron(rule, db)
                ):
                    continue

                media_paths: list[str] = []
                aggregator = self._pipeline_executor.event_aggregator
                if rule.primary_sensor_id and aggregator:
                    media_paths = await aggregator.get_recent_images(
                        rule.primary_sensor_id, limit=3
                    )

                trigger = TriggerContext(
                    trigger_type="cron",
                    sensor_id=rule.primary_sensor_id,
                    room_name=None,
                    media_paths=media_paths,
                )

                await self._pipeline_executor.execute(rule, trigger, db)
                logger.info(
                    "periodic_rule_executed",
                    rule_id=rule.id,
                    rule_name=rule.name,
                    cron_trigger_name=ct.name,
                )
        except Exception:
            logger.exception("periodic_rule_error", cron_trigger_id=cron_trigger_id)
        finally:
            db.close()

    async def resume_workflow(self, execution_id: int) -> None:
        """Resume a waiting workflow execution (called by APScheduler)."""
        if not self._pipeline_executor:
            logger.warning(
                "cannot_resume_workflow",
                execution_id=execution_id,
                reason="executor not set",
            )
            return

        db: Session = self._db_session_factory()
        try:
            await self._pipeline_executor.resume(execution_id, db)
            logger.info("workflow_resumed", execution_id=execution_id)
        except Exception:
            logger.exception("workflow_resume_error", execution_id=execution_id)
        finally:
            db.close()

    # -- internal helpers ---------------------------------------------------

    def _load_rule_jobs(self) -> None:
        """Query DB for enabled cron triggers and register APScheduler jobs.

        One job is created per CronTrigger (not per Rule). When the job fires,
        all rules linked to that trigger via rule_cron_triggers are evaluated
        through RulesEngine and executed if they pass.
        """
        db: Session = self._db_session_factory()
        app_tz = _app_timezone()
        try:
            stmt = select(CronTrigger).where(CronTrigger.enabled.is_(True))
            triggers: list[CronTrigger] = list(db.execute(stmt).scalars().all())

            for ct in triggers:
                job_id = f"cron_{ct.id}"
                trigger_tz = ZoneInfo(ct.timezone) if ct.timezone else app_tz
                try:
                    trigger = ApschedulerCronTrigger.from_crontab(
                        ct.expression, timezone=trigger_tz
                    )
                except ValueError:
                    logger.warning(
                        "invalid_cron_expression",
                        cron_trigger_id=ct.id,
                        expression=ct.expression,
                    )
                    continue

                self._scheduler.add_job(
                    self.execute_periodic_rule,
                    trigger=trigger,
                    args=[ct.id],
                    id=job_id,
                    name=f"Cron: {ct.name}",
                    replace_existing=True,
                )
                logger.info(
                    "cron_trigger_job_added",
                    job_id=job_id,
                    cron_trigger_name=ct.name,
                    expression=ct.expression,
                    timezone=str(trigger_tz),
                )

            logger.info("cron_trigger_jobs_loaded", count=len(triggers))
        finally:
            db.close()

    def _schedule_pending_resumes(self) -> None:
        """On startup, re-schedule resume jobs for any waiting executions."""
        from backend.models.pipeline import WorkflowExecution

        db: Session = self._db_session_factory()
        try:
            waiting = (
                db.query(WorkflowExecution)
                .filter(
                    WorkflowExecution.status == "waiting",
                    WorkflowExecution.resume_at.isnot(None),
                )
                .all()
            )
            for execution in waiting:
                job_id = f"resume_{execution.id}"
                resume_at_iso = execution.resume_at.isoformat() if execution.resume_at else ""
                self._scheduler.add_job(
                    self.resume_workflow,
                    trigger=DateTrigger(run_date=execution.resume_at),
                    args=[execution.id],
                    id=job_id,
                    name=f"Resume workflow #{execution.id}",
                    replace_existing=True,
                )
                logger.info(
                    "pending_resume_rescheduled",
                    execution_id=execution.id,
                    resume_at=resume_at_iso,
                )
            if waiting:
                logger.info("pending_resumes_loaded", count=len(waiting))
        finally:
            db.close()


class SchedulerBridge:
    """Thin adapter passed to :class:`PipelineExecutor` so it can schedule
    workflow resume jobs without importing this module directly.

    Accepts either a :class:`Scheduler` (preferred) or a raw
    ``AsyncIOScheduler`` (legacy, for backward compatibility with call sites
    that still pass the underlying apscheduler object).
    """

    def __init__(self, scheduler: Scheduler | AsyncIOScheduler) -> None:
        if isinstance(scheduler, Scheduler):
            self._owner: Scheduler | None = scheduler
            self._scheduler = scheduler.apscheduler
        else:
            self._owner = None
            self._scheduler = scheduler

    @property
    def apscheduler(self) -> AsyncIOScheduler:
        """The underlying ``AsyncIOScheduler`` (for ``add_job`` etc.)."""
        return self._scheduler

    def schedule_workflow_resume(self, execution_id: int, resume_at: datetime) -> None:
        if self._owner is not None:
            self._owner.schedule_workflow_resume(execution_id, resume_at)
            return

        job_id = f"resume_{execution_id}"
        self._scheduler.add_job(
            _resume_workflow_callback,
            trigger=DateTrigger(run_date=resume_at),
            args=[execution_id],
            id=job_id,
            name=f"Resume workflow #{execution_id}",
            replace_existing=True,
        )
        logger.info(
            "workflow_resume_scheduled",
            execution_id=execution_id,
            resume_at=resume_at.isoformat(),
        )


# ---------------------------------------------------------------------------
# Module-level facade
# ---------------------------------------------------------------------------
#
# The module-level ``_pipeline_executor`` and ``_db_session_factory`` globals
# are preserved because ``backend.mcp.server.trigger_rule`` imports
# ``_pipeline_executor`` directly. They mirror the most recently configured
# :class:`Scheduler` instance.

_default_scheduler: Scheduler | None = None
_pipeline_executor: Any = None
_db_session_factory: Callable[[], Session] | None = None


def setup_scheduler(
    event_aggregator: EventAggregator,
    db_session_factory: Callable[[], Session],
    pipeline_executor: Any = None,
    *,
    rules_engine: Any = None,
) -> AsyncIOScheduler:
    """Create and configure the default :class:`Scheduler`, returning its
    underlying ``AsyncIOScheduler`` for backward compatibility.
    """
    global _default_scheduler, _pipeline_executor, _db_session_factory
    instance = Scheduler(
        event_aggregator=event_aggregator,
        db_session_factory=db_session_factory,
        pipeline_executor=pipeline_executor,
        rules_engine=rules_engine,
    )
    instance.configure()
    _default_scheduler = instance
    _pipeline_executor = pipeline_executor
    _db_session_factory = db_session_factory
    return instance.apscheduler


def reload_scheduled_rules(
    scheduler: AsyncIOScheduler,
    db_session_factory: Callable[[], Session],
) -> None:
    """Remove all rule-based jobs and re-add them from the database.

    Prefers the default :class:`Scheduler` instance (so job callbacks remain
    bound methods); falls back to a transient instance for tests that pass
    in a bare ``AsyncIOScheduler``.
    """
    if _default_scheduler is not None and _default_scheduler.apscheduler is scheduler:
        _default_scheduler.reload_rules()
        return

    # Legacy path: rebuild jobs against the caller's bare scheduler.
    for job in scheduler.get_jobs():
        if job.id.startswith("cron_"):
            scheduler.remove_job(job.id)
            logger.debug("cron_job_removed", job_id=job.id)

    tz = _app_timezone()
    db: Session = db_session_factory()
    try:
        stmt = select(CronTrigger).where(CronTrigger.enabled.is_(True))
        for ct in db.execute(stmt).scalars().all():
            trigger_tz = ZoneInfo(ct.timezone) if ct.timezone else tz
            try:
                trigger = ApschedulerCronTrigger.from_crontab(ct.expression, timezone=trigger_tz)
            except ValueError:
                logger.warning(
                    "invalid_cron_expression",
                    cron_trigger_id=ct.id,
                    expression=ct.expression,
                )
                continue
            scheduler.add_job(
                execute_periodic_rule,
                trigger=trigger,
                args=[ct.id, db_session_factory],
                id=f"cron_{ct.id}",
                name=f"Cron: {ct.name}",
                replace_existing=True,
            )
    finally:
        db.close()
    logger.info("scheduled_rules_reloaded")


async def execute_periodic_rule(
    cron_trigger_id: int,
    db_session_factory: Callable[[], Session],
) -> None:
    """Module-level facade kept for the legacy job-args code path."""
    if _default_scheduler is not None:
        await _default_scheduler.execute_periodic_rule(cron_trigger_id)
        return

    if not _pipeline_executor:
        logger.warning("pipeline_executor_not_set", cron_trigger_id=cron_trigger_id)
        return

    logger.warning("execute_periodic_rule_legacy_path", cron_trigger_id=cron_trigger_id)


async def _resume_workflow_callback(execution_id: int) -> None:
    """Module-level facade kept for legacy ``SchedulerBridge`` usage."""
    if _default_scheduler is not None:
        await _default_scheduler.resume_workflow(execution_id)
        return

    if not _pipeline_executor or not _db_session_factory:
        logger.warning(
            "cannot_resume_workflow",
            execution_id=execution_id,
            reason="executor or db factory not set",
        )
        return

    db: Session = _db_session_factory()
    try:
        await _pipeline_executor.resume(execution_id, db)
        logger.info("workflow_resumed", execution_id=execution_id)
    except Exception:
        logger.exception("workflow_resume_error", execution_id=execution_id)
    finally:
        db.close()


def reset_default_scheduler() -> None:
    """Test helper: clear the module-level facade state."""
    global _default_scheduler, _pipeline_executor, _db_session_factory
    _default_scheduler = None
    _pipeline_executor = None
    _db_session_factory = None
