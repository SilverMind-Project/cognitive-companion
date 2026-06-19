"""SQL-backed guided-task metrics aggregation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Integer, case, false, func, select, true
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.core.config import settings as default_settings
from backend.core.time import normalize_utc_datetime
from backend.models.guided_task import GuidedSession, GuidedSessionEvent
from backend.schemas.guided_metrics import (
    GuidedAbandonmentEnvelope,
    GuidedAttemptsPerStepEnvelope,
    GuidedCompletionSummaryEnvelope,
    GuidedEscalationBreakdownEnvelope,
    GuidedEscalationMetric,
    GuidedMetricsDashboardEnvelope,
    GuidedMetricsWindow,
    GuidedOutcomeCount,
    GuidedReasonCount,
    GuidedRoutineDurationMetric,
    GuidedStepAttemptMetric,
    GuidedTimeOfDayBucket,
    GuidedTimeOfDayEnvelope,
    GuidedTimeToCompleteEnvelope,
    GuidedVisionAgreementEnvelope,
)


class GuidedMetricsService:
    """Read-only metrics service for caregiver-facing guided-task observability."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        settings: Settings | None = None,
        time_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._db_factory = db_factory
        self._settings = settings or default_settings
        self._time_fn = time_fn or (lambda: datetime.now(UTC))

    def completion_summary(
        self,
        *,
        person_id: str,
        routine_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> GuidedCompletionSummaryEnvelope:
        window = self._window(person_id=person_id, routine_id=routine_id, since=since, until=until)
        db = self._db_factory()
        try:
            base = self._session_filters(window)
            started = int(
                db.execute(select(func.count(GuidedSession.id)).where(*base)).scalar_one()
            )
            outcome_expr = func.coalesce(GuidedSession.outcome, GuidedSession.status)
            rows = db.execute(
                select(
                    outcome_expr.label("outcome"),
                    func.count(GuidedSession.id),
                )
                .where(*base)
                .group_by(outcome_expr)
                .order_by(outcome_expr)
            ).all()
        finally:
            db.close()

        outcomes = [GuidedOutcomeCount(outcome=str(row[0]), count=int(row[1])) for row in rows]
        completed = sum(item.count for item in outcomes if item.outcome == "completed")
        return GuidedCompletionSummaryEnvelope(
            window=window,
            started=started,
            completed=completed,
            completion_rate=self._rate(completed, started),
            outcomes=outcomes,
        )

    def attempts_per_step(
        self,
        *,
        person_id: str,
        routine_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> GuidedAttemptsPerStepEnvelope:
        window = self._window(person_id=person_id, routine_id=routine_id, since=since, until=until)
        db = self._db_factory()
        try:
            per_session = (
                select(
                    GuidedSessionEvent.step_ord.label("step_ord"),
                    GuidedSessionEvent.session_id.label("session_id"),
                    func.count(GuidedSessionEvent.id).label("attempts"),
                )
                .join(GuidedSession, GuidedSession.id == GuidedSessionEvent.session_id)
                .where(
                    *self._session_filters(window),
                    GuidedSessionEvent.kind == "retry",
                    GuidedSessionEvent.step_ord.isnot(None),
                )
                .group_by(GuidedSessionEvent.step_ord, GuidedSessionEvent.session_id)
                .subquery()
            )
            rows = db.execute(
                select(
                    per_session.c.step_ord,
                    func.avg(per_session.c.attempts),
                    func.max(per_session.c.attempts),
                    func.sum(per_session.c.attempts),
                )
                .group_by(per_session.c.step_ord)
                .order_by(per_session.c.step_ord)
            ).all()
        finally:
            db.close()

        return GuidedAttemptsPerStepEnvelope(
            window=window,
            items=[
                GuidedStepAttemptMetric(
                    step_ord=int(row[0]),
                    average_attempts=float(row[1] or 0.0),
                    max_attempts=int(row[2] or 0),
                    retry_events=int(row[3] or 0),
                )
                for row in rows
            ],
        )

    def time_to_complete(
        self,
        *,
        person_id: str,
        routine_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> GuidedTimeToCompleteEnvelope:
        window = self._window(person_id=person_id, routine_id=routine_id, since=since, until=until)
        duration_s = func.extract("epoch", GuidedSession.completed_at - GuidedSession.started_at)
        db = self._db_factory()
        try:
            rows = db.execute(
                select(
                    GuidedSession.routine_id,
                    func.count(GuidedSession.id),
                    func.avg(duration_s),
                    func.percentile_cont(0.5).within_group(duration_s),
                )
                .where(
                    *self._session_filters(window),
                    GuidedSession.completed_at.isnot(None),
                    GuidedSession.outcome.in_(("completed", "escalated_resolved")),
                )
                .group_by(GuidedSession.routine_id)
                .order_by(GuidedSession.routine_id)
            ).all()
        finally:
            db.close()

        return GuidedTimeToCompleteEnvelope(
            window=window,
            items=[
                GuidedRoutineDurationMetric(
                    routine_id=int(row[0]),
                    sessions=int(row[1]),
                    average_seconds=float(row[2] or 0.0),
                    median_seconds=float(row[3] or 0.0),
                )
                for row in rows
            ],
        )

    def abandonment(
        self,
        *,
        person_id: str,
        routine_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> GuidedAbandonmentEnvelope:
        window = self._window(person_id=person_id, routine_id=routine_id, since=since, until=until)
        db = self._db_factory()
        try:
            started = int(
                db.execute(
                    select(func.count(GuidedSession.id)).where(*self._session_filters(window))
                ).scalar_one()
            )
            abandoned = int(
                db.execute(
                    select(func.count(GuidedSession.id)).where(
                        *self._session_filters(window),
                        GuidedSession.outcome.in_(
                            ("abandoned", "summon_timeout", "escalated_unanswered")
                        ),
                    )
                ).scalar_one()
            )
            rows = db.execute(
                select(
                    func.coalesce(
                        GuidedSessionEvent.detail["reason"].astext,
                        GuidedSessionEvent.detail["outcome"].astext,
                        "unknown",
                    ).label("reason"),
                    func.count(GuidedSessionEvent.id),
                )
                .join(GuidedSession, GuidedSession.id == GuidedSessionEvent.session_id)
                .where(
                    *self._session_filters(window),
                    GuidedSessionEvent.kind == "session_abandoned",
                )
                .group_by("reason")
                .order_by("reason")
            ).all()
        finally:
            db.close()

        return GuidedAbandonmentEnvelope(
            window=window,
            abandoned=abandoned,
            started=started,
            abandonment_rate=self._rate(abandoned, started),
            reasons=[GuidedReasonCount(reason=str(row[0]), count=int(row[1])) for row in rows],
        )

    def escalation_breakdown(
        self,
        *,
        person_id: str,
        routine_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> GuidedEscalationBreakdownEnvelope:
        window = self._window(person_id=person_id, routine_id=routine_id, since=since, until=until)
        emergency_expr = self._json_bool(GuidedSessionEvent.detail, "emergency")
        db = self._db_factory()
        try:
            rows = db.execute(
                select(
                    func.coalesce(GuidedSessionEvent.detail["reason"].astext, "unknown").label(
                        "reason"
                    ),
                    emergency_expr.label("emergency"),
                    func.count(GuidedSessionEvent.id),
                )
                .join(GuidedSession, GuidedSession.id == GuidedSessionEvent.session_id)
                .where(
                    *self._session_filters(window),
                    GuidedSessionEvent.kind.in_(("help_requested", "escalation")),
                )
                .group_by("reason", "emergency")
                .order_by("reason", "emergency")
            ).all()
        finally:
            db.close()

        items = [
            GuidedEscalationMetric(reason=str(row[0]), emergency=bool(row[1]), count=int(row[2]))
            for row in rows
        ]
        return GuidedEscalationBreakdownEnvelope(
            window=window,
            total=sum(item.count for item in items),
            emergency_total=sum(item.count for item in items if item.emergency),
            items=items,
        )

    def vision_agreement(
        self,
        *,
        person_id: str,
        routine_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> GuidedVisionAgreementEnvelope:
        window = self._window(person_id=person_id, routine_id=routine_id, since=since, until=until)
        agreed_expr = self._json_bool(GuidedSessionEvent.detail, "agreed")
        uncertain_expr = self._json_bool(GuidedSessionEvent.detail, "uncertain")
        db = self._db_factory()
        try:
            row = db.execute(
                select(
                    func.count(GuidedSessionEvent.id),
                    func.coalesce(func.sum(case((agreed_expr.is_(true()), 1), else_=0)), 0),
                    func.coalesce(func.sum(case((uncertain_expr.is_(true()), 1), else_=0)), 0),
                )
                .join(GuidedSession, GuidedSession.id == GuidedSessionEvent.session_id)
                .where(
                    *self._session_filters(window),
                    GuidedSessionEvent.kind == "vision_confirm",
                )
            ).one()
        finally:
            db.close()

        total = int(row[0])
        agreed = int(row[1])
        return GuidedVisionAgreementEnvelope(
            window=window,
            total=total,
            agreed=agreed,
            uncertain=int(row[2]),
            agreement_rate=self._rate(agreed, total),
        )

    def time_of_day(
        self,
        *,
        person_id: str,
        routine_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> GuidedTimeOfDayEnvelope:
        window = self._window(person_id=person_id, routine_id=routine_id, since=since, until=until)
        tz_name = self._settings.as_str("app.timezone")
        local_hour = func.extract("hour", func.timezone(tz_name, GuidedSession.started_at)).cast(
            Integer
        )
        completed_expr = GuidedSession.outcome.in_(("completed", "escalated_resolved"))
        abandoned_expr = GuidedSession.outcome.in_(
            ("abandoned", "summon_timeout", "escalated_unanswered")
        )
        db = self._db_factory()
        try:
            rows = db.execute(
                select(
                    local_hour.label("hour"),
                    func.count(GuidedSession.id),
                    func.coalesce(func.sum(case((completed_expr, 1), else_=0)), 0),
                    func.coalesce(func.sum(case((abandoned_expr, 1), else_=0)), 0),
                )
                .where(*self._session_filters(window))
                .group_by("hour")
                .order_by("hour")
            ).all()
        finally:
            db.close()

        by_hour = {
            int(row[0]): GuidedTimeOfDayBucket(
                hour=int(row[0]), started=int(row[1]), completed=int(row[2]), abandoned=int(row[3])
            )
            for row in rows
        }
        return GuidedTimeOfDayEnvelope(
            window=window,
            timezone=tz_name,
            buckets=[
                by_hour.get(
                    hour, GuidedTimeOfDayBucket(hour=hour, started=0, completed=0, abandoned=0)
                )
                for hour in range(24)
            ],
        )

    def dashboard(
        self,
        *,
        person_id: str,
        routine_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> GuidedMetricsDashboardEnvelope:
        return GuidedMetricsDashboardEnvelope(
            completion=self.completion_summary(
                person_id=person_id, routine_id=routine_id, since=since, until=until
            ),
            attempts_per_step=self.attempts_per_step(
                person_id=person_id, routine_id=routine_id, since=since, until=until
            ),
            time_to_complete=self.time_to_complete(
                person_id=person_id, routine_id=routine_id, since=since, until=until
            ),
            abandonment=self.abandonment(
                person_id=person_id, routine_id=routine_id, since=since, until=until
            ),
            escalation_breakdown=self.escalation_breakdown(
                person_id=person_id, routine_id=routine_id, since=since, until=until
            ),
            vision_agreement=self.vision_agreement(
                person_id=person_id, routine_id=routine_id, since=since, until=until
            ),
            time_of_day=self.time_of_day(
                person_id=person_id, routine_id=routine_id, since=since, until=until
            ),
        )

    def _window(
        self,
        *,
        person_id: str,
        routine_id: int | None,
        since: datetime | None,
        until: datetime | None,
    ) -> GuidedMetricsWindow:
        until_utc = normalize_utc_datetime(until) or self._now()
        since_utc = normalize_utc_datetime(since) or (until_utc - timedelta(days=30))
        return GuidedMetricsWindow(
            person_id=person_id,
            routine_id=routine_id,
            since=since_utc,
            until=until_utc,
        )

    def _session_filters(self, window: GuidedMetricsWindow) -> list[Any]:
        filters: list[Any] = [
            GuidedSession.person_id == window.person_id,
            GuidedSession.started_at >= window.since,
            GuidedSession.started_at < window.until,
        ]
        if window.routine_id is not None:
            filters.append(GuidedSession.routine_id == window.routine_id)
        return filters

    def _now(self) -> datetime:
        now = self._time_fn()
        if now.tzinfo is None:
            raise ValueError("GuidedMetricsService time_fn must return timezone-aware datetimes")
        return now.astimezone(UTC)

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator, 4)

    @staticmethod
    def _json_bool(json_column: Any, key: str) -> Any:
        return case(
            (json_column[key].astext == "true", true()),
            (json_column[key].astext == "false", false()),
            else_=false(),
        )
