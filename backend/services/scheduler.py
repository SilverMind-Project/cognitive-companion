"""APScheduler setup — periodic rule execution, workflow resume, and maintenance.

Provides:
- Cron-based rule scheduling from the database
- One-shot resume jobs for waiting workflow executions
- Periodic media cleanup
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.rule import Rule
from backend.services.event_aggregator import EventAggregator

logger = get_logger(__name__)

# Module-level reference set during setup — allows the resume callback to
# locate the pipeline executor without circular imports.
_pipeline_executor = None
_db_session_factory: Callable[[], Session] | None = None


def setup_scheduler(
    event_aggregator: EventAggregator,
    db_session_factory: Callable[[], Session],
    pipeline_executor=None,
) -> AsyncIOScheduler:
    """Create, configure, and return an :class:`AsyncIOScheduler`.

    * Loads all enabled rules that have a ``schedule_cron`` value and
      registers them as cron jobs.
    * Adds an interval job for media cleanup.
    * Stores *pipeline_executor* for use by periodic rule execution and
      workflow resume callbacks.
    """
    global _pipeline_executor, _db_session_factory
    _pipeline_executor = pipeline_executor
    _db_session_factory = db_session_factory

    scheduler = AsyncIOScheduler()

    # -- maintenance jobs -----------------------------------------------------
    scheduler.add_job(
        event_aggregator.cleanup_expired_media,
        trigger=IntervalTrigger(minutes=5),
        id="cleanup_expired_media",
        name="Cleanup expired media objects",
        replace_existing=True,
    )
    logger.info("scheduler_maintenance_job_added", job="cleanup_expired_media")

    # -- scheduled rules ------------------------------------------------------
    _load_rule_jobs(scheduler, db_session_factory)

    # -- resume waiting workflows on startup ----------------------------------
    _schedule_pending_resumes(scheduler, db_session_factory)

    logger.info("scheduler_setup_complete")
    return scheduler


def reload_scheduled_rules(
    scheduler: AsyncIOScheduler,
    db_session_factory: Callable[[], Session],
) -> None:
    """Remove all rule-based jobs and re-add them from the database."""
    existing_jobs = scheduler.get_jobs()
    for job in existing_jobs:
        if job.id.startswith("rule_"):
            scheduler.remove_job(job.id)
            logger.debug("rule_job_removed", job_id=job.id)

    _load_rule_jobs(scheduler, db_session_factory)
    logger.info("scheduled_rules_reloaded")


class SchedulerBridge:
    """Thin wrapper passed to :class:`PipelineExecutor` so it can schedule
    workflow resume jobs without importing the scheduler module directly.
    """

    def __init__(self, scheduler: AsyncIOScheduler) -> None:
        self._scheduler = scheduler

    def schedule_workflow_resume(
        self, execution_id: int, resume_at: datetime
    ) -> None:
        """Register a one-shot APScheduler job that resumes a workflow."""
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
# Callbacks
# ---------------------------------------------------------------------------


async def execute_periodic_rule(
    rule_id: int,
    db_session_factory: Callable[[], Session],
) -> None:
    """Execute a periodic rule via the pipeline executor."""
    if not _pipeline_executor:
        logger.warning("pipeline_executor_not_set", rule_id=rule_id)
        return

    from backend.services.pipeline_executor import TriggerContext

    db: Session = db_session_factory()
    try:
        rule = db.get(Rule, rule_id)
        if rule is None:
            logger.warning("periodic_rule_not_found", rule_id=rule_id)
            return

        if not rule.enabled:
            logger.debug("periodic_rule_disabled", rule_id=rule_id, name=rule.name)
            return

        # For periodic rules, capture from primary sensor if configured
        media_paths: list[str] = []
        if rule.primary_sensor_id:

            # Try to get recent images from the primary sensor
            # The aggregator is available via the pipeline executor
            if _pipeline_executor._aggregator:
                media_paths = await _pipeline_executor._aggregator.get_recent_images(
                    rule.primary_sensor_id, limit=3
                )

        trigger = TriggerContext(
            trigger_type="cron",
            sensor_id=rule.primary_sensor_id,
            room_name=None,
            media_paths=media_paths,
        )

        await _pipeline_executor.execute(rule, trigger, db)
        logger.info(
            "periodic_rule_executed",
            rule_id=rule_id,
            name=rule.name,
            schedule_cron=rule.schedule_cron,
        )
    except Exception:
        logger.exception("periodic_rule_error", rule_id=rule_id)
    finally:
        db.close()


async def _resume_workflow_callback(execution_id: int) -> None:
    """Called by APScheduler to resume a waiting workflow execution."""
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_rule_jobs(
    scheduler: AsyncIOScheduler,
    db_session_factory: Callable[[], Session],
) -> None:
    """Query DB for enabled rules with a cron schedule and register them."""
    db: Session = db_session_factory()
    try:
        stmt = select(Rule).where(
            Rule.enabled.is_(True),
            Rule.schedule_cron.isnot(None),
        )
        rules: list[Rule] = list(db.execute(stmt).scalars().all())

        for rule in rules:
            job_id = f"rule_{rule.id}"
            try:
                trigger = CronTrigger.from_crontab(rule.schedule_cron)  # type: ignore[arg-type]
            except ValueError:
                logger.warning(
                    "invalid_cron_expression",
                    rule_id=rule.id,
                    schedule_cron=rule.schedule_cron,
                )
                continue

            scheduler.add_job(
                execute_periodic_rule,
                trigger=trigger,
                args=[rule.id, db_session_factory],
                id=job_id,
                name=f"Rule: {rule.name}",
                replace_existing=True,
            )
            logger.info(
                "rule_job_added",
                job_id=job_id,
                rule_name=rule.name,
                cron=rule.schedule_cron,
            )

        logger.info("rule_jobs_loaded", count=len(rules))
    finally:
        db.close()


def _schedule_pending_resumes(
    scheduler: AsyncIOScheduler,
    db_session_factory: Callable[[], Session],
) -> None:
    """On startup, re-schedule resume jobs for any waiting executions."""
    from backend.models.pipeline import WorkflowExecution

    db: Session = db_session_factory()
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
            scheduler.add_job(
                _resume_workflow_callback,
                trigger=DateTrigger(run_date=execution.resume_at),
                args=[execution.id],
                id=job_id,
                name=f"Resume workflow #{execution.id}",
                replace_existing=True,
            )
            logger.info(
                "pending_resume_rescheduled",
                execution_id=execution.id,
                resume_at=execution.resume_at.isoformat(),
            )
        if waiting:
            logger.info("pending_resumes_loaded", count=len(waiting))
    finally:
        db.close()
