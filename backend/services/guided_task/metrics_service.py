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
    GuidedGateCostSummaryEnvelope,
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
    GuidedWatchSummaryEnvelope,
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
        agreed_expr = case(
            (GuidedSessionEvent.detail["complete"].astext == "true", true()),
            (GuidedSessionEvent.detail["agreed"].astext == "true", true()),
            else_=false(),
        )
        min_conf = 0.7
        if self._settings is not None:
            import contextlib

            with contextlib.suppress(Exception):
                min_conf = self._settings.as_float("guided_task.vision.confirm.min_confidence")

        from sqlalchemy import Float

        uncertain_expr = case(
            (GuidedSessionEvent.detail["uncertain"].astext == "true", true()),
            (
                case(
                    (
                        GuidedSessionEvent.detail["confidence"].astext.isnot(None),
                        GuidedSessionEvent.detail["confidence"].astext.cast(Float) < min_conf,
                    ),
                    else_=false(),
                ).is_(true()),
                true(),
            ),
            else_=false(),
        )
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

    def watch_summary(
        self,
        *,
        person_id: str,
        routine_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> GuidedWatchSummaryEnvelope:
        window = self._window(person_id=person_id, routine_id=routine_id, since=since, until=until)
        db = self._db_factory()
        try:
            filters = self._session_filters(window)
            total_runs = int(
                db.execute(
                    select(func.count(GuidedSessionEvent.id))
                    .join(GuidedSession, GuidedSession.id == GuidedSessionEvent.session_id)
                    .where(*filters, GuidedSessionEvent.kind == "watch")
                ).scalar_one()
            )

            auto_advances = int(
                db.execute(
                    select(func.count(GuidedSessionEvent.id))
                    .join(GuidedSession, GuidedSession.id == GuidedSessionEvent.session_id)
                    .where(
                        *filters,
                        GuidedSessionEvent.kind == "step_completed",
                        GuidedSessionEvent.detail["completion_reason"].astext
                        == "watch_auto_advance",
                    )
                ).scalar_one()
            )

            watch_events_stmt = (
                select(GuidedSessionEvent)
                .join(GuidedSession, GuidedSession.id == GuidedSessionEvent.session_id)
                .where(*filters, GuidedSessionEvent.kind == "watch")
                .order_by(
                    GuidedSessionEvent.session_id,
                    GuidedSessionEvent.step_ord,
                    GuidedSessionEvent.at,
                )
            )
            watch_events = list(db.execute(watch_events_stmt).scalars().all())

            confirm_events_stmt = (
                select(GuidedSessionEvent)
                .join(GuidedSession, GuidedSession.id == GuidedSessionEvent.session_id)
                .where(*filters, GuidedSessionEvent.kind == "vision_confirm")
                .order_by(
                    GuidedSessionEvent.session_id,
                    GuidedSessionEvent.step_ord,
                    GuidedSessionEvent.at,
                )
            )
            confirm_events = list(db.execute(confirm_events_stmt).scalars().all())
        finally:
            db.close()

        total_model_calls = 0
        total_frames = 0
        total_latency_ms = 0.0
        for e in watch_events:
            cost = (e.detail or {}).get("cost") or {}
            total_model_calls += cost.get("model_calls", 0)
            total_frames += cost.get("frames", 0)
            total_latency_ms += cost.get("latency_ms", 0.0)

        avg_model_calls = (total_model_calls / total_runs) if total_runs > 0 else 0.0
        avg_frames = (total_frames / total_runs) if total_runs > 0 else 0.0
        avg_latency_ms = (total_latency_ms / total_runs) if total_runs > 0 else 0.0

        from collections import defaultdict

        watch_by_step = defaultdict(list)
        for e in watch_events:
            watch_by_step[(e.session_id, e.step_ord)].append(e)

        agreed_comparisons = 0
        total_comparisons = 0

        for c_event in confirm_events:
            step_watches = watch_by_step.get((c_event.session_id, c_event.step_ord))
            if not step_watches:
                continue

            last_watch = None
            for w in step_watches:
                if w.at < c_event.at:
                    last_watch = w
                else:
                    break

            if last_watch is not None:
                total_comparisons += 1
                c_detail = c_event.detail or {}
                c_complete = c_detail.get("complete")
                if c_complete is None:
                    c_complete = c_detail.get("agreed")

                w_detail = last_watch.detail or {}
                w_complete = w_detail.get("complete")
                if w_complete is None:
                    w_complete = w_detail.get("agreed")

                if w_complete == c_complete:
                    agreed_comparisons += 1

        agreement_rate = (agreed_comparisons / total_comparisons) if total_comparisons > 0 else 0.0

        return GuidedWatchSummaryEnvelope(
            window=window,
            total_runs=total_runs,
            auto_advances=auto_advances,
            agreement_rate=agreement_rate,
            average_model_calls=avg_model_calls,
            average_frames=avg_frames,
            average_latency_ms=avg_latency_ms,
        )

    def gate_cost_summary(
        self,
        *,
        person_id: str,
        routine_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> GuidedGateCostSummaryEnvelope:
        window = self._window(person_id=person_id, routine_id=routine_id, since=since, until=until)
        db = self._db_factory()
        try:
            filters = self._session_filters(window)
            events_stmt = (
                select(GuidedSessionEvent)
                .join(GuidedSession, GuidedSession.id == GuidedSessionEvent.session_id)
                .where(
                    *filters,
                    GuidedSessionEvent.kind.in_(("watch", "vision_confirm")),
                )
            )
            events = list(db.execute(events_stmt).scalars().all())
        finally:
            db.close()

        confirm_model_calls = 0
        confirm_frames = 0
        confirm_latency_ms = 0.0
        watch_model_calls = 0
        watch_frames = 0
        watch_latency_ms = 0.0

        for e in events:
            cost = (e.detail or {}).get("cost") or {}
            m_calls = cost.get("model_calls", 0)
            frames = cost.get("frames", 0)
            latency = cost.get("latency_ms", 0.0)

            if e.kind == "vision_confirm":
                confirm_model_calls += m_calls
                confirm_frames += frames
                confirm_latency_ms += latency
            elif e.kind == "watch":
                watch_model_calls += m_calls
                watch_frames += frames
                watch_latency_ms += latency

        from backend.schemas.guided_metrics import GuidedGateCostMetric

        return GuidedGateCostSummaryEnvelope(
            window=window,
            confirm_cost=GuidedGateCostMetric(
                model_calls=confirm_model_calls,
                frames=confirm_frames,
                latency_ms=confirm_latency_ms,
            ),
            watch_cost=GuidedGateCostMetric(
                model_calls=watch_model_calls,
                frames=watch_frames,
                latency_ms=watch_latency_ms,
            ),
            total_cost=GuidedGateCostMetric(
                model_calls=confirm_model_calls + watch_model_calls,
                frames=confirm_frames + watch_frames,
                latency_ms=confirm_latency_ms + watch_latency_ms,
            ),
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
            watch_summary=self.watch_summary(
                person_id=person_id, routine_id=routine_id, since=since, until=until
            ),
            gate_cost_summary=self.gate_cost_summary(
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
