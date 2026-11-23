from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.services.interactive_session import (
    cancel_session_timeout,
    resume_owning_pipeline,
    schedule_session_timeout,
)
from backend.services.scheduler import Scheduler, SchedulerBridge


@dataclass
class _FakeApscheduler:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def add_job(
        self,
        finalize: Any,
        trigger: str,
        *,
        run_date: datetime,
        id: str,
        args: list[Any],
        replace_existing: bool,
    ) -> None:
        self.calls.append(
            {
                "finalize": finalize,
                "trigger": trigger,
                "run_date": run_date,
                "id": id,
                "args": args,
                "replace_existing": replace_existing,
            }
        )


@dataclass
class _FakeScheduler:
    apscheduler: _FakeApscheduler = field(default_factory=_FakeApscheduler)


async def _finalize(session_id: int) -> None:
    return None


def test_schedule_session_timeout_adds_job() -> None:
    scheduler = _FakeScheduler()
    run_at = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)

    schedule_session_timeout(
        scheduler,
        job_id="quiz_timeout_7",
        run_at=run_at,
        finalize=_finalize,
        args=[7],
    )

    assert scheduler.apscheduler.calls == [
        {
            "finalize": _finalize,
            "trigger": "date",
            "run_date": run_at,
            "id": "quiz_timeout_7",
            "args": [7],
            "replace_existing": True,
        }
    ]


def test_schedule_session_timeout_no_scheduler_warns() -> None:
    schedule_session_timeout(
        None,
        job_id="quiz_timeout_7",
        run_at=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        finalize=_finalize,
        args=[7],
    )


class _RecordingResumeScheduler:
    def __init__(self, *, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.calls: list[tuple[int, datetime]] = []

    def schedule_workflow_resume(self, execution_id: int, resume_at: datetime) -> None:
        self.calls.append((execution_id, resume_at))
        if self.should_raise:
            raise RuntimeError("scheduler down")


_NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


def test_resume_owning_pipeline_schedules_resume_now() -> None:
    scheduler = _RecordingResumeScheduler()

    resume_owning_pipeline(scheduler, 42, now=_NOW)

    assert scheduler.calls == [(42, _NOW)]


def test_resume_owning_pipeline_missing_execution_id_noop() -> None:
    scheduler = _RecordingResumeScheduler()

    resume_owning_pipeline(scheduler, None, now=_NOW)

    assert scheduler.calls == []


def test_resume_owning_pipeline_without_scheduler_is_logged_not_raised() -> None:
    resume_owning_pipeline(None, 42, now=_NOW)


def test_resume_owning_pipeline_scheduler_raises_is_logged_not_raised() -> None:
    scheduler = _RecordingResumeScheduler(should_raise=True)

    resume_owning_pipeline(scheduler, 42, now=_NOW)

    assert scheduler.calls == [(42, _NOW)]


async def test_resume_owning_pipeline_replaces_the_wait_until_fallback_job() -> None:
    """The early resume must supersede the executor's wait_until job, not run beside it."""
    raw = AsyncIOScheduler()
    raw.start(paused=True)
    try:
        bridge = SchedulerBridge(raw)
        later = datetime(2026, 11, 22, 12, 10, tzinfo=UTC)
        bridge.schedule_workflow_resume(42, later)

        resume_owning_pipeline(bridge, 42, now=_NOW)

        jobs = [job for job in raw.get_jobs() if job.id == "resume_42"]
    finally:
        raw.shutdown(wait=False)
    assert len(jobs) == 1
    assert jobs[0].trigger.run_date == _NOW


class _AwaitedExecutor:
    """An async ``resume`` like ``PipelineExecutor.resume``: proves it is awaited, not dropped."""

    def __init__(self) -> None:
        self.resumed = asyncio.Event()
        self.execution_ids: list[int] = []

    async def resume(self, execution_id: int, db: object) -> None:
        self.execution_ids.append(execution_id)
        self.resumed.set()


class _ClosingDb:
    def close(self) -> None:
        return None


async def test_resume_owning_pipeline_actually_runs_the_async_executor_resume() -> None:
    executor = _AwaitedExecutor()
    owner = Scheduler(
        event_aggregator=None,
        db_session_factory=_ClosingDb,
        pipeline_executor=executor,
    )
    owner.apscheduler.start()
    try:
        resume_owning_pipeline(SchedulerBridge(owner), 42, now=datetime.now(UTC))
        await asyncio.wait_for(executor.resumed.wait(), timeout=5)
    finally:
        owner.apscheduler.shutdown(wait=False)

    assert executor.execution_ids == [42]


def test_cancel_session_timeout_removes_pending_job_and_tolerates_missing() -> None:
    raw = AsyncIOScheduler()
    bridge = SchedulerBridge(raw)
    schedule_session_timeout(
        bridge,
        job_id="quiz_timeout_7",
        run_at=_NOW,
        finalize=_finalize,
        args=[7],
    )

    cancel_session_timeout(bridge, job_id="quiz_timeout_7")
    cancel_session_timeout(bridge, job_id="quiz_timeout_7")
    cancel_session_timeout(None, job_id="quiz_timeout_7")

    assert raw.get_job("quiz_timeout_7") is None


class _Aggregator:
    async def cleanup_expired_media(self) -> None:
        return None


async def test_resume_runs_through_the_production_wiring(db_factory, monkeypatch) -> None:
    """Production wraps the raw APScheduler returned by ``setup_scheduler`` in a
    ``SchedulerBridge``, which resumes through the module-level callback. Prove that
    path awaits the async executor resume too."""
    import backend.services.scheduler as scheduler_module

    for name in ("_default_scheduler", "_pipeline_executor", "_db_session_factory"):
        monkeypatch.setattr(scheduler_module, name, None)
    executor = _AwaitedExecutor()
    raw = scheduler_module.setup_scheduler(_Aggregator(), db_factory, executor)
    raw.start()
    try:
        resume_owning_pipeline(SchedulerBridge(raw), 42, now=datetime.now(UTC))
        await asyncio.wait_for(executor.resumed.wait(), timeout=5)
    finally:
        raw.shutdown(wait=False)

    assert executor.execution_ids == [42]
