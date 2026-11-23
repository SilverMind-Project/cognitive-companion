"""Link an interactive session (quiz, guided task) to the pipeline execution parked on it."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from apscheduler.jobstores.base import JobLookupError

from backend.core.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class WorkflowResumeScheduler(Protocol):
    """The slice of ``SchedulerBridge`` an interactive session needs to resume its pipeline."""

    def schedule_workflow_resume(self, execution_id: int, resume_at: datetime) -> None: ...


def schedule_session_timeout(
    scheduler: Any,
    *,
    job_id: str,
    run_at: datetime,
    finalize: Callable,
    args: list[Any],
) -> None:
    """Schedule a one-shot timeout job for an interactive session."""
    if scheduler is None:
        logger.warning("interactive_session_no_scheduler", job_id=job_id)
        return

    try:
        scheduler.apscheduler.add_job(
            finalize,
            "date",
            run_date=run_at,
            id=job_id,
            args=args,
            replace_existing=True,
        )
        logger.info("interactive_session_timeout_scheduled", job_id=job_id)
    except Exception:
        logger.exception("interactive_session_timeout_schedule_failed", job_id=job_id)


def cancel_session_timeout(scheduler: Any, *, job_id: str) -> None:
    """Remove a pending session timeout job; a job that already ran or never existed is fine."""
    if scheduler is None:
        return
    try:
        scheduler.apscheduler.remove_job(job_id)
        logger.info("interactive_session_timeout_cancelled", job_id=job_id)
    except JobLookupError:
        return


def resume_owning_pipeline(
    scheduler: WorkflowResumeScheduler | None,
    execution_id: int | None,
    *,
    now: datetime | None = None,
) -> None:
    """Resume the pipeline parked on this session, if one exists.

    The resume is scheduled for ``now`` rather than awaited inline. Callers run inside
    a realtime tool call or a WebSocket handler, and the rest of the pipeline must not
    block them. Scheduling under the executor's own ``resume_{execution_id}`` job id
    also replaces the fallback resume the executor registered at the step's
    ``wait_until``, so the pipeline resumes exactly once.
    """
    if not execution_id:
        return
    if not isinstance(scheduler, WorkflowResumeScheduler):
        logger.warning(
            "interactive_session_resume_unavailable",
            execution_id=execution_id,
            reason="no_scheduler",
        )
        return
    try:
        scheduler.schedule_workflow_resume(execution_id, now or datetime.now(UTC))
    except Exception:
        logger.exception("interactive_session_resume_failed", execution_id=execution_id)
