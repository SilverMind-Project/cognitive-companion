"""Admission control for local (Spark-hosted) vision/text LLM calls.

One DGX Spark serves the Triton model zoo, the vLLM vision model, the
llama.cpp reasoning model, and TTS simultaneously. Nothing bounds how many
heavy vision calls stack concurrently across rules, the guided-task confirm
profile, and a future watch tick. ``LLMAdmissionController`` is the single
choke point at the provider boundary: every local provider (``openai_compat``,
``ollama``) wraps its network call in ``admit()`` so no caller can bypass it.
The cloud realtime provider (Gemini) is exempt by construction, it never
touches this controller.

Two lanes exist because vision requests are the memory-bandwidth hogs and
text requests are cheaper but still compete for the same GPU. A queued
request that cannot start within ``queue_timeout_s`` fails closed with
:class:`LLMAdmissionTimeout` rather than piling up indefinitely.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from backend.core.logging import get_logger

logger = get_logger(__name__)

Lane = Literal["vision", "text"]
Outcome = Literal["ok", "timeout", "error"]


class LLMAdmissionTimeout(Exception):
    """Raised when a queued admission request exceeds ``queue_timeout_s``.

    A gate must never hang a resident interaction behind a queue: callers
    convert this into a fail-closed result rather than letting it propagate
    as a generic error (``llm_call`` -> structured failed ``StepResult``;
    the gate runner's existing per-node exception handling already fails
    the node closed).
    """

    def __init__(self, lane: Lane, caller: str, waited_s: float) -> None:
        self.lane = lane
        self.caller = caller
        self.waited_s = waited_s
        super().__init__(
            f"LLM admission timeout: lane={lane} caller={caller} waited_s={waited_s:.1f}"
        )


@dataclass(frozen=True)
class AdmissionRecord:
    """One completed (or timed-out) admission, for the telemetry ring buffer."""

    caller: str
    lane: Lane
    model_id: str | None
    queue_wait_ms: int
    execution_ms: int
    outcome: Outcome
    at: datetime  # time_fn() wall-clock timestamp at record time (UTC)


class LLMAdmissionController:
    """Two-lane semaphore gate in front of local LLM providers.

    ``time_fn`` is an injectable wall clock (per the project's clock-injection
    rule), used both to measure queue-wait/execution durations and to
    timestamp each :class:`AdmissionRecord` for telemetry's calendar bucketing
    (calls-per-hour). It is not the actual timeout mechanism: that uses
    ``asyncio.wait_for``'s own event-loop clock, which cannot be faked from
    outside without patching the loop, the same tradeoff
    ``GateGraphRunner``'s per-node timeout accepts.
    """

    def __init__(
        self,
        *,
        max_concurrent_vision: int = 1,
        max_concurrent_text: int = 2,
        queue_timeout_s: float = 20.0,
        time_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
        ring_buffer_size: int = 2000,
    ) -> None:
        self._queue_timeout_s = queue_timeout_s
        self._time_fn = time_fn
        self._semaphores: dict[Lane, asyncio.Semaphore] = {
            "vision": asyncio.Semaphore(max_concurrent_vision),
            "text": asyncio.Semaphore(max_concurrent_text),
        }
        self._waiting: dict[Lane, int] = {"vision": 0, "text": 0}
        self._records: deque[AdmissionRecord] = deque(maxlen=ring_buffer_size)
        self._counters: dict[tuple[str, str, str], int] = {}

    def admit(self, lane: Lane, caller: str, *, model_id: str | None = None) -> _Admission:
        """Return an async context manager that gates entry on the lane's semaphore.

        Usage::

            async with controller.admit("vision", caller="rule:tea_intent") as _ticket:
                return await _do_the_network_call()
        """
        return _Admission(self, lane, caller, model_id)

    def queue_depth(self, lane: Lane) -> int:
        """Number of admissions currently waiting (not yet acquired) on *lane*."""
        return self._waiting[lane]

    def snapshot(self) -> list[AdmissionRecord]:
        """Return a copy of the ring buffer, oldest first."""
        return list(self._records)

    def counters(self) -> dict[tuple[str, str, str], int]:
        """Return a copy of the (caller, lane, outcome) -> count counters."""
        return dict(self._counters)

    @property
    def ring_buffer_capacity(self) -> int:
        """Configured maximum size of the telemetry ring buffer."""
        return self._records.maxlen or 0

    def _record(self, record: AdmissionRecord) -> None:
        self._records.append(record)
        key = (record.caller, record.lane, record.outcome)
        self._counters[key] = self._counters.get(key, 0) + 1


class _Admission:
    """Async context manager returned by :meth:`LLMAdmissionController.admit`."""

    __slots__ = ("_acquired_at", "_caller", "_controller", "_lane", "_model_id", "_queue_wait_ms")

    def __init__(
        self, controller: LLMAdmissionController, lane: Lane, caller: str, model_id: str | None
    ) -> None:
        self._controller = controller
        self._lane = lane
        self._caller = caller
        self._model_id = model_id
        self._queue_wait_ms = 0
        self._acquired_at: datetime | None = None

    async def __aenter__(self) -> _Admission:
        controller = self._controller
        start = controller._time_fn()
        controller._waiting[self._lane] += 1
        try:
            try:
                await asyncio.wait_for(
                    controller._semaphores[self._lane].acquire(),
                    timeout=controller._queue_timeout_s,
                )
            except TimeoutError as exc:
                now = controller._time_fn()
                waited_s = (now - start).total_seconds()
                controller._record(
                    AdmissionRecord(
                        caller=self._caller,
                        lane=self._lane,
                        model_id=self._model_id,
                        queue_wait_ms=int(waited_s * 1000),
                        execution_ms=0,
                        outcome="timeout",
                        at=now,
                    )
                )
                logger.warning(
                    "llm_admission_timeout",
                    lane=self._lane,
                    caller=self._caller,
                    waited_s=waited_s,
                )
                raise LLMAdmissionTimeout(self._lane, self._caller, waited_s) from exc
        finally:
            controller._waiting[self._lane] -= 1
        self._acquired_at = controller._time_fn()
        self._queue_wait_ms = int((self._acquired_at - start).total_seconds() * 1000)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        controller = self._controller
        now = controller._time_fn()
        acquired_at = self._acquired_at if self._acquired_at is not None else now
        execution_ms = int((now - acquired_at).total_seconds() * 1000)
        outcome: Outcome = "ok" if exc_type is None else "error"
        controller._semaphores[self._lane].release()
        controller._record(
            AdmissionRecord(
                caller=self._caller,
                lane=self._lane,
                model_id=self._model_id,
                queue_wait_ms=self._queue_wait_ms,
                execution_ms=execution_ms,
                outcome=outcome,
                at=now,
            )
        )
