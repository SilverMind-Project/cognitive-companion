"""Pure guided-task state machine."""

from __future__ import annotations

from datetime import datetime

from backend.services.guided_task.domain import (
    TERMINAL_STATUSES,
    Decision,
    ResolvedPolicy,
    SessionView,
    StepView,
)


class GuidedTaskStateMachine:
    """Deterministic state machine for guided-task sessions."""

    @staticmethod
    def decide(
        session: SessionView,
        step: StepView,
        event: str,
        policy: ResolvedPolicy,
        now: datetime,
        *,
        evidence: dict | None = None,
    ) -> Decision:
        if session.status in TERMINAL_STATUSES:
            return Decision.hold(session, "noop", "terminal_session")

        if event == "step_completed":
            if step.min_duration_s is not None:
                elapsed_s = (now - session.step_entered_at).total_seconds()
                if elapsed_s < step.min_duration_s:
                    return Decision.hold(session, "wait", "min_duration_not_elapsed")
            if session.current_step_ord == session.num_steps - 1:
                return Decision(
                    kind="complete",
                    next_status="completed",
                    next_step_ord=session.current_step_ord,
                    attempts=0,
                    reason="completed_last_step",
                )
            return Decision(
                kind="advance",
                next_status="active",
                next_step_ord=session.current_step_ord + 1,
                attempts=0,
                reason="step_completed",
            )

        if event == "skip_condition_met":
            if session.current_step_ord == session.num_steps - 1:
                return Decision(
                    kind="complete",
                    next_status="completed",
                    next_step_ord=session.current_step_ord,
                    attempts=0,
                    reason="skipped_last",
                )
            return Decision(
                kind="skip",
                next_status="active",
                next_step_ord=session.current_step_ord + 1,
                attempts=0,
                reason="skip_condition_met",
            )

        if event == "timeout_tick":
            # Vision progress delays the ladder (no nagging a resident who is
            # visibly working) but never cancels it: once the step has used its
            # whole ladder budget, a caregiver is told instead.
            progress_seen_at = (evidence or {}).get("progress_seen_at")
            if (
                progress_seen_at is not None
                and (now - progress_seen_at).total_seconds() < policy.step_timeout_s
            ):
                on_step_s = (now - session.step_entered_at).total_seconds()
                if on_step_s < policy.step_timeout_s * policy.max_step_attempts:
                    return Decision.hold(session, "noop", "nag_suppressed")
                return Decision(
                    kind="escalate",
                    next_status="escalated",
                    next_step_ord=session.current_step_ord,
                    attempts=session.attempts,
                    reason="step_overrun_with_progress",
                )
            if session.attempts + 1 >= policy.max_step_attempts:
                return Decision(
                    kind="escalate",
                    next_status="escalated",
                    next_step_ord=session.current_step_ord,
                    attempts=session.attempts + 1,
                    reason="attempts_exhausted",
                )
            return Decision(
                kind="retry",
                next_status="active",
                next_step_ord=session.current_step_ord,
                attempts=session.attempts + 1,
                reason="timeout_retry",
            )

        if event == "safety_event":
            event_evidence = evidence or {}
            severity = event_evidence.get("severity")
            emergency = severity == "emergency" or (step.is_safety_critical and severity == "high")
            return Decision(
                kind="escalate",
                next_status="escalated",
                next_step_ord=session.current_step_ord,
                attempts=session.attempts,
                reason=str(event_evidence.get("condition") or "safety_event"),
                emergency=emergency,
            )

        if event == "caregiver_takeover":
            return Decision(
                kind="takeover",
                next_status="caregiver_takeover",
                next_step_ord=session.current_step_ord,
                attempts=session.attempts,
                reason="caregiver_takeover",
            )

        if event == "resume":
            if (now - session.last_activity_at).total_seconds() <= policy.resume_grace_s:
                return Decision(
                    kind="retry",
                    next_status="active",
                    next_step_ord=session.current_step_ord,
                    attempts=session.attempts,
                    reason="resumed",
                )
            return Decision(
                kind="abandon",
                next_status="abandoned",
                next_step_ord=session.current_step_ord,
                attempts=session.attempts,
                reason="resume_grace_exceeded",
            )

        return Decision.hold(session, "noop", "unhandled_event")
