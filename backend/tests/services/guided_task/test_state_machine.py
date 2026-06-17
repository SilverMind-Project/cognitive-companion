from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.services.guided_task.domain import ResolvedPolicy, SessionView, StepView
from backend.services.guided_task.state_machine import GuidedTaskStateMachine

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)


def _session(**overrides) -> SessionView:
    values = {
        "status": "active",
        "current_step_ord": 0,
        "attempts": 0,
        "num_steps": 2,
        "started_at": NOW - timedelta(minutes=5),
        "last_activity_at": NOW - timedelta(seconds=30),
        "step_entered_at": NOW - timedelta(seconds=30),
    }
    values.update(overrides)
    return SessionView(**values)


def _step(**overrides) -> StepView:
    values = {
        "ord": 0,
        "has_skip_condition": False,
        "min_duration_s": None,
        "is_safety_critical": False,
    }
    values.update(overrides)
    return StepView(**values)


def _policy(**overrides) -> ResolvedPolicy:
    values = {"step_timeout_s": 300, "max_step_attempts": 3, "resume_grace_s": 600}
    values.update(overrides)
    return ResolvedPolicy(**values)


def test_step_completed_not_last_advances():
    decision = GuidedTaskStateMachine.decide(
        _session(), _step(), "step_completed", _policy(), NOW
    )

    assert decision.kind == "advance"
    assert decision.next_step_ord == 1
    assert decision.attempts == 0


def test_step_completed_last_completes():
    decision = GuidedTaskStateMachine.decide(
        _session(current_step_ord=1), _step(ord=1), "step_completed", _policy(), NOW
    )

    assert decision.kind == "complete"
    assert decision.next_status == "completed"


def test_step_completed_before_min_duration_waits():
    decision = GuidedTaskStateMachine.decide(
        _session(step_entered_at=NOW - timedelta(seconds=10)),
        _step(min_duration_s=60),
        "step_completed",
        _policy(),
        NOW,
    )

    assert decision.kind == "wait"
    assert decision.reason == "min_duration_not_elapsed"
    assert decision.next_step_ord == 0


def test_skip_condition_advances_and_marks_skipped():
    decision = GuidedTaskStateMachine.decide(
        _session(), _step(has_skip_condition=True), "skip_condition_met", _policy(), NOW
    )

    assert decision.kind == "skip"
    assert decision.next_step_ord == 1
    assert decision.attempts == 0


def test_skip_condition_on_last_completes():
    decision = GuidedTaskStateMachine.decide(
        _session(current_step_ord=1),
        _step(ord=1, has_skip_condition=True),
        "skip_condition_met",
        _policy(),
        NOW,
    )

    assert decision.kind == "complete"
    assert decision.reason == "skipped_last"


def test_timeout_under_attempt_cap_retries_increments_attempts():
    decision = GuidedTaskStateMachine.decide(
        _session(attempts=1), _step(), "timeout_tick", _policy(max_step_attempts=3), NOW
    )

    assert decision.kind == "retry"
    assert decision.attempts == 2


def test_timeout_at_attempt_cap_escalates():
    decision = GuidedTaskStateMachine.decide(
        _session(attempts=2), _step(), "timeout_tick", _policy(max_step_attempts=3), NOW
    )

    assert decision.kind == "escalate"
    assert decision.reason == "attempts_exhausted"


def test_safety_emergency_escalates_with_emergency_flag():
    decision = GuidedTaskStateMachine.decide(
        _session(),
        _step(),
        "safety_event",
        _policy(),
        NOW,
        evidence={"severity": "emergency"},
    )

    assert decision.kind == "escalate"
    assert decision.emergency is True


def test_safety_critical_step_high_severity_is_emergency():
    decision = GuidedTaskStateMachine.decide(
        _session(),
        _step(is_safety_critical=True),
        "safety_event",
        _policy(),
        NOW,
        evidence={"severity": "high"},
    )

    assert decision.emergency is True


def test_non_emergency_safety_escalates_without_flag():
    decision = GuidedTaskStateMachine.decide(
        _session(),
        _step(),
        "safety_event",
        _policy(),
        NOW,
        evidence={"severity": "medium"},
    )

    assert decision.kind == "escalate"
    assert decision.emergency is False


def test_caregiver_takeover_sets_status():
    decision = GuidedTaskStateMachine.decide(
        _session(), _step(), "caregiver_takeover", _policy(), NOW
    )

    assert decision.kind == "takeover"
    assert decision.next_status == "caregiver_takeover"


def test_resume_within_grace_retries():
    decision = GuidedTaskStateMachine.decide(
        _session(last_activity_at=NOW - timedelta(seconds=599)),
        _step(),
        "resume",
        _policy(resume_grace_s=600),
        NOW,
    )

    assert decision.kind == "retry"
    assert decision.reason == "resumed"


def test_resume_after_grace_abandons():
    decision = GuidedTaskStateMachine.decide(
        _session(last_activity_at=NOW - timedelta(seconds=601)),
        _step(),
        "resume",
        _policy(resume_grace_s=600),
        NOW,
    )

    assert decision.kind == "abandon"
    assert decision.next_status == "abandoned"


def test_terminal_session_any_event_noop():
    decision = GuidedTaskStateMachine.decide(
        _session(status="completed"), _step(), "step_completed", _policy(), NOW
    )

    assert decision.kind == "noop"
    assert decision.reason == "terminal_session"
