from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.core.logging import get_logger

logger = get_logger(__name__)


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


def resume_owning_pipeline(
    pipeline_executor: Any,
    db_factory: Callable[[], Session],
    execution_id: int | None,
) -> None:
    """Resume the pipeline parked on this session, if one exists."""
    if not execution_id or pipeline_executor is None:
        return

    db: Session = db_factory()
    try:
        pipeline_executor.resume(execution_id, db)
    except Exception:
        logger.exception("interactive_session_resume_failed", execution_id=execution_id)
    finally:
        db.close()
