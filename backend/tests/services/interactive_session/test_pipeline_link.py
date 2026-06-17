from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.services.interactive_session import (
    resume_owning_pipeline,
    schedule_session_timeout,
)


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


class _FakeDb:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakePipelineExecutor:
    def __init__(self, *, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.calls: list[tuple[int, _FakeDb]] = []

    def resume(self, execution_id: int, db: _FakeDb) -> None:
        self.calls.append((execution_id, db))
        if self.should_raise:
            raise RuntimeError("resume failed")


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


def test_resume_owning_pipeline_calls_resume() -> None:
    db = _FakeDb()
    executor = _FakePipelineExecutor()

    resume_owning_pipeline(executor, lambda: db, 42)

    assert executor.calls == [(42, db)]
    assert db.closed is True


def test_resume_owning_pipeline_missing_execution_id_noop() -> None:
    executor = _FakePipelineExecutor()

    resume_owning_pipeline(executor, lambda: _FakeDb(), None)

    assert executor.calls == []


def test_resume_owning_pipeline_executor_raises_is_logged_not_raised() -> None:
    db = _FakeDb()
    executor = _FakePipelineExecutor(should_raise=True)

    resume_owning_pipeline(executor, lambda: db, 42)

    assert executor.calls == [(42, db)]
    assert db.closed is True
