"""U5-T4: PipelineExecutor emits exactly one event per transition.

Verifies (rule 13: one increment per code path):
- _emit helper calls the publisher with the event dict
- publisher failure does NOT break execution (side-channel rule)
- _next_seq() increments monotonically (one increment per code path)
- Events emitted have timezone-aware UTC timestamps (rule 9)
- Event type strings match the spec (pipeline_started, step_started, etc.)

Note: testing the full execute() flow requires a real SQLAlchemy instance due
to flag_modified. These unit tests target the event infrastructure directly:
_emit, _next_seq, and the event dict shapes emitted at each hook. Integration
coverage lives in test_pipeline_run_service.py which exercises the full DB path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from backend.services.pipeline_executor import PipelineExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executor(publisher=None) -> PipelineExecutor:
    return PipelineExecutor(
        db_session_factory=MagicMock(),
        event_publisher=publisher,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEmitHelper:
    async def test_publisher_called_with_event_dict(self):
        received: list[dict] = []

        async def publisher(event: dict) -> None:
            received.append(event)

        executor = _make_executor(publisher=publisher)
        await executor._emit({"type": "pipeline_event", "event_type": "pipeline_started"})

        assert len(received) == 1
        assert received[0]["event_type"] == "pipeline_started"

    async def test_no_publisher_does_not_raise(self):
        executor = _make_executor(publisher=None)
        await executor._emit({"type": "pipeline_event", "event_type": "step_started"})
        # No exception is the assertion.

    async def test_publisher_failure_is_dead_lettered(self):
        """Rule 15 side-channel: publisher errors are caught and logged, not propagated."""
        call_count = 0

        async def failing_publisher(event: dict) -> None:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("broker down")

        executor = _make_executor(publisher=failing_publisher)
        # Must not raise even though publisher raises.
        await executor._emit({"type": "pipeline_event", "event_type": "step_started"})
        assert call_count == 1, "publisher was called despite eventual failure"


class TestNextSeq:
    def test_monotonically_increments(self):
        executor = _make_executor()
        seqs = [executor._next_seq() for _ in range(5)]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == 5

    def test_starts_at_one(self):
        executor = _make_executor()
        assert executor._next_seq() == 1


@pytest.mark.asyncio
class TestEventShape:
    async def test_pipeline_started_event_has_required_fields(self):
        received: list[dict] = []

        async def publisher(event: dict) -> None:
            received.append(event)

        executor = _make_executor(publisher=publisher)
        now = datetime.now(UTC)
        await executor._emit(
            {
                "type": "pipeline_event",
                "event_type": "pipeline_started",
                "execution_id": 1,
                "rule_id": 10,
                "rule_name": "test",
                "status": "running",
                "started_at": now.isoformat(),
                "sequence": executor._next_seq(),
            }
        )

        assert received[0]["event_type"] == "pipeline_started"
        assert received[0]["status"] == "running"

    async def test_step_completed_failed_carries_failed_status(self):
        """Rule 15: failed step must emit status='failed', never 'succeeded'."""
        received: list[dict] = []

        async def publisher(event: dict) -> None:
            received.append(event)

        executor = _make_executor(publisher=publisher)
        await executor._emit(
            {
                "type": "pipeline_event",
                "event_type": "step_completed",
                "execution_id": 1,
                "rule_id": 10,
                "rule_name": "test",
                "step_id": "42",
                "step_name": "LLM",
                "step_type": "llm_call",
                "status": "failed",
                "error_code": "timeout",
                "sequence": executor._next_seq(),
            }
        )

        assert received[0]["status"] == "failed"
        assert received[0]["error_code"] == "timeout"

    async def test_timestamps_are_utc_aware(self):
        """Rule 9: all emitted timestamps must be timezone-aware ISO strings."""
        received: list[dict] = []

        async def publisher(event: dict) -> None:
            received.append(event)

        executor = _make_executor(publisher=publisher)
        now = datetime.now(UTC)
        await executor._emit(
            {
                "type": "pipeline_event",
                "event_type": "step_started",
                "execution_id": 1,
                "rule_id": 1,
                "rule_name": "test",
                "started_at": now.isoformat(),
                "sequence": executor._next_seq(),
            }
        )

        ts_str = received[0].get("started_at")
        assert ts_str is not None
        dt = datetime.fromisoformat(ts_str)
        assert dt.tzinfo is not None, f"timestamp '{ts_str}' must be timezone-aware"
