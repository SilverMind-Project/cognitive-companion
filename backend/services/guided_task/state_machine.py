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
            return Decision(
                kind="noop",
                next_status=session.status,
                next_step_ord=session.current_step_ord,
                attempts=session.attempts,
                reason="terminal_session",
            )

        if event == "step_completed":
            if step.min_duration_s is not None:
                elapsed_s = (now - session.step_entered_at).total_seconds()
                if elapsed_s < step.min_duration_s:
                    return Decision(
                        kind="wait",
                        next_status=session.status,
                        next_step_ord=session.current_step_ord,
                        attempts=session.attempts,
                        reason="min_duration_not_elapsed",
                    )
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
            severity = (evidence or {}).get("severity")
            emergency = severity == "emergency" or (step.is_safety_critical and severity == "high")
            return Decision(
                kind="escalate",
                next_status="escalated",
                next_step_ord=session.current_step_ord,
                attempts=session.attempts,
                reason="safety_event",
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

        return Decision(
            kind="noop",
            next_status=session.status,
            next_step_ord=session.current_step_ord,
            attempts=session.attempts,
            reason="unhandled_event",
        )
