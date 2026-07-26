"""Unit tests for :class:`~backend.services.inference_telemetry.InferenceTelemetryService`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.integrations.llm.admission import LLMAdmissionController
from backend.services.inference_telemetry import InferenceTelemetryService


class _FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


async def _record(
    controller: LLMAdmissionController, lane: str, caller: str, *, raise_error: bool = False
) -> None:
    if raise_error:
        try:
            async with controller.admit(lane, caller):
                raise RuntimeError("boom")
        except RuntimeError:
            pass
    else:
        async with controller.admit(lane, caller):
            pass


class TestInferenceTelemetryService:
    async def test_empty_controller_returns_zeroed_telemetry(self) -> None:
        controller = LLMAdmissionController()
        svc = InferenceTelemetryService(controller)

        telemetry = svc.get_telemetry()

        assert telemetry.totals_by_caller_lane == []
        assert telemetry.queue_wait_p50_ms is None
        assert telemetry.queue_wait_p95_ms is None
        assert telemetry.timeouts_total == 0
        assert telemetry.calls_per_hour == []
        assert {q.lane for q in telemetry.queue_depth} == {"vision", "text"}
        assert all(q.depth == 0 for q in telemetry.queue_depth)

    async def test_totals_grouped_by_caller_and_lane(self) -> None:
        controller = LLMAdmissionController()
        svc = InferenceTelemetryService(controller)

        await _record(controller, "vision", "rule:a")
        await _record(controller, "vision", "rule:a")
        await _record(controller, "vision", "rule:a", raise_error=True)
        await _record(controller, "text", "rule:b")

        telemetry = svc.get_telemetry()
        by_key = {(r.caller, r.lane): r for r in telemetry.totals_by_caller_lane}

        assert by_key[("rule:a", "vision")].ok == 2
        assert by_key[("rule:a", "vision")].error == 1
        assert by_key[("rule:b", "text")].ok == 1

    async def test_window_excludes_records_older_than_window_minutes(self) -> None:
        clock = _FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
        controller = LLMAdmissionController(time_fn=clock)
        svc = InferenceTelemetryService(controller, window_minutes=60, time_fn=clock)

        await _record(controller, "text", "rule:old")
        clock.advance(minutes=90)
        await _record(controller, "text", "rule:new")

        telemetry = svc.get_telemetry()
        callers = {r.caller for r in telemetry.totals_by_caller_lane}
        assert callers == {"rule:new"}

    async def test_calls_per_hour_bucketed_by_utc_hour_and_lane(self) -> None:
        clock = _FakeClock(datetime(2026, 1, 1, 14, 10, tzinfo=UTC))
        controller = LLMAdmissionController(time_fn=clock)
        svc = InferenceTelemetryService(controller, window_minutes=180, time_fn=clock)

        await _record(controller, "vision", "rule:a")
        clock.advance(minutes=20)
        await _record(controller, "vision", "rule:a")
        clock.advance(hours=1)
        await _record(controller, "vision", "rule:a")

        telemetry = svc.get_telemetry()
        assert len(telemetry.calls_per_hour) == 2
        first_hour = next(b for b in telemetry.calls_per_hour if b.hour.startswith("2026-01-01T14"))
        assert first_hour.calls == 2

    async def test_ring_buffer_size_and_capacity_reported(self) -> None:
        controller = LLMAdmissionController(ring_buffer_size=5)
        svc = InferenceTelemetryService(controller)

        await _record(controller, "text", "rule:a")
        await _record(controller, "text", "rule:a")

        telemetry = svc.get_telemetry()
        assert telemetry.ring_buffer_size == 2
        assert telemetry.ring_buffer_capacity == 5
