"""Daily report compilation service.

Generates end-of-day structured summary reports aggregating:
- Sleep duration and quality
- Meal occurrences
- Medication adherence
- Bathroom visits
- Door events
- Exercise sessions
- Room location time distribution
- Optional LLM-generated prose summary
- Wellness score and alert flags
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.core.time import UTC
from backend.services.person_location.types import RoomSegment

logger = get_logger(__name__)


class PersonLocationReader(Protocol):
    async def room_segments(
        self, person_id: str, start: datetime, end: datetime
    ) -> tuple[RoomSegment, ...]: ...


def _serialize_datetime(obj: Any) -> Any:
    """Serialize datetime objects to ISO format strings for JSON."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class DailyReportService:
    """Service for generating and managing daily reports.

    This service aggregates data from multiple sources to create structured
    daily reports. It supports both automatic generation at midnight and
    on-demand regeneration.

    Graceful degradation: all dependent service calls return None/[] without
    raising when services (semantic-memory-service, scene-analysis-service)
    are unavailable.
    """

    def __init__(
        self,
        db_session_factory,
        scene_analysis_client=None,
        person_location_service: PersonLocationReader | None = None,
    ):
        """Initialize the service.

        Args:
            db_session_factory: Callable that returns a new DB Session.
            scene_analysis_client: Optional SceneAnalysisClient for room trends.
            person_location_service: Backs the room-time aggregation. ``None``
                when CTS is disabled (bootstrap sets it later via
                ``set_person_location_service`` once the CTS phase runs);
                room-time degrades to an empty distribution rather than erroring.
        """
        self._db_session_factory = db_session_factory
        self._scene_analysis_client = scene_analysis_client
        self._person_location = person_location_service

    def set_person_location_service(
        self, person_location_service: PersonLocationReader | None
    ) -> None:
        self._person_location = person_location_service

    async def generate_daily_report(
        self,
        person_id: str,
        date: str,
        tz_name: str = "UTC",
        include_llm_summary: bool = False,
        include_room_trends: bool = False,
    ) -> dict:
        """Generate a daily report for a person on a specific date.

        Args:
            person_id: Household member ID.
            date: Date string in YYYY-MM-DD format.
            tz_name: Timezone for date interpretation.
            include_llm_summary: Whether to generate LLM prose summary.
            include_room_trends: Whether to include room trend data.

        Returns:
            Daily report dict with all aggregated metrics.
        """
        db = self._db_session_factory()
        try:
            # Compute UTC range for the date
            tz = ZoneInfo(tz_name)
            day_start = datetime(int(date[:4]), int(date[5:7]), int(date[8:]), tzinfo=tz)
            day_end = day_start + timedelta(days=1)

            day_start_utc = day_start.astimezone(UTC)
            day_end_utc = day_end.astimezone(UTC)

            # Initialize report structure
            report = {
                "person_id": person_id,
                "report_date": date,
                "tz_name": tz_name,
                "generated_at": datetime.now(UTC),
                "sleep": self._aggregate_sleep(db, person_id, day_start_utc, day_end_utc),
                "meals": self._aggregate_meals(db, person_id, day_start_utc, day_end_utc),
                "medication": self._aggregate_medication(db, person_id, day_start_utc, day_end_utc),
                "bathroom_visits": self._aggregate_bathroom(
                    db, person_id, day_start_utc, day_end_utc
                ),
                "exercise": self._aggregate_exercise(db, person_id, day_start_utc, day_end_utc),
                "tv": self._aggregate_tv(db, person_id, day_start_utc, day_end_utc),
                "room_time": await self._aggregate_room_time(person_id, day_start_utc, day_end_utc),
                "summary_text": None,
                "wellness_score": None,
                "wellness_alerts": [],
            }

            # Optional LLM summary
            if include_llm_summary:
                report["summary_text"] = self._generate_llm_summary(report)

            # Optional room trends
            if include_room_trends and self._scene_analysis_client:
                report["room_trends"] = self._get_room_trends(person_id, date, tz_name)

            # Compute wellness score and alerts
            report["wellness_score"], report["wellness_alerts"] = self._compute_wellness(report)

            # Update or create DB record
            self._upsert_report_db(db, person_id, date, report)

            logger.info(
                "daily_report_generated",
                person_id=person_id,
                date=date,
                wellness_score=report["wellness_score"],
            )

            return report
        except Exception:
            logger.exception("daily_report_generation_error", person_id=person_id, date=date)
            db.rollback()
            raise
        finally:
            db.close()

    def _aggregate_sleep(self, db: Session, person_id: str, start: datetime, end: datetime) -> dict:
        """Aggregate sleep data from activity sessions.

        Sleep sessions are attributed to the day they close (not the day they open),
        so a session that starts at 8pm yesterday and ends at 4am today is counted
        as today's sleep.
        """
        from backend.models.person import ActivitySession

        stmt = select(ActivitySession).where(
            and_(
                ActivitySession.person_id == person_id,
                ActivitySession.activity_type == "sleep",
                ActivitySession.status == "closed",
                and_(ActivitySession.closed_at >= start, ActivitySession.closed_at < end),
            )
        )

        sessions = db.execute(stmt).scalars().all()

        total_minutes = sum(s.duration_minutes or 0 for s in sessions)
        session_count = len(sessions)

        # Simple quality score based on continuity (no disruptions)
        quality_score = (
            min(1.0, total_minutes / 480) if session_count > 0 else 0.0
        )  # 8 hours target

        return {
            "total_minutes": total_minutes,
            "session_count": session_count,
            "quality_score": round(quality_score, 2),
            "disruptions": max(0, session_count - 1),  # Multiple sessions = potential disruptions
        }

    def _aggregate_meals(self, db: Session, person_id: str, start: datetime, end: datetime) -> dict:
        """Aggregate meal data from activity sessions."""
        from backend.models.person import ActivitySession

        meal_types = ["meal_prep", "meal_eating"]
        sessions = (
            db.execute(
                select(ActivitySession).where(
                    and_(
                        ActivitySession.person_id == person_id,
                        ActivitySession.activity_type.in_(meal_types),
                        ActivitySession.status == "closed",
                        or_(
                            and_(
                                ActivitySession.opened_at >= start, ActivitySession.opened_at < end
                            ),
                            and_(
                                ActivitySession.closed_at >= start, ActivitySession.closed_at < end
                            ),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )

        prep_count = sum(1 for s in sessions if s.activity_type == "meal_prep")
        eating_count = sum(1 for s in sessions if s.activity_type == "meal_eating")

        meal_durations = [s.duration_minutes for s in sessions if s.duration_minutes]
        avg_duration = sum(meal_durations) / len(meal_durations) if meal_durations else None

        return {
            "prep_count": prep_count,
            "eating_count": eating_count,
            "avg_duration_minutes": round(avg_duration, 1) if avg_duration else None,
        }

    def _aggregate_medication(
        self, db: Session, person_id: str, start: datetime, end: datetime
    ) -> dict:
        """Aggregate medication data from activity sessions."""
        from backend.models.person import ActivitySession

        sessions = (
            db.execute(
                select(ActivitySession).where(
                    and_(
                        ActivitySession.person_id == person_id,
                        ActivitySession.activity_type == "medication",
                        ActivitySession.status == "closed",
                        or_(
                            and_(
                                ActivitySession.opened_at >= start, ActivitySession.opened_at < end
                            ),
                            and_(
                                ActivitySession.closed_at >= start, ActivitySession.closed_at < end
                            ),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )

        doses_taken = len(sessions)
        # Doses due would come from config/settings - placeholder
        doses_due = 3  # Typical: morning, afternoon, evening

        adherence_pct = (doses_taken / doses_due * 100) if doses_due > 0 else 0.0

        return {
            "doses_taken": doses_taken,
            "doses_due": doses_due,
            "adherence_pct": round(adherence_pct, 1),
        }

    def _aggregate_bathroom(
        self, db: Session, person_id: str, start: datetime, end: datetime
    ) -> dict:
        """Aggregate bathroom visit data from activity sessions."""
        from backend.models.person import ActivitySession

        sessions = (
            db.execute(
                select(ActivitySession).where(
                    and_(
                        ActivitySession.person_id == person_id,
                        ActivitySession.activity_type == "bathroom",
                        ActivitySession.status == "closed",
                        or_(
                            and_(
                                ActivitySession.opened_at >= start, ActivitySession.opened_at < end
                            ),
                            and_(
                                ActivitySession.closed_at >= start, ActivitySession.closed_at < end
                            ),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )

        visit_count = len(sessions)
        total_minutes = sum(s.duration_minutes or 0 for s in sessions)
        avg_minutes = total_minutes / visit_count if visit_count > 0 else None

        return {
            "visit_count": visit_count,
            "total_minutes": total_minutes,
            "avg_duration_minutes": round(avg_minutes, 1) if avg_minutes else None,
        }

    def _aggregate_exercise(
        self, db: Session, person_id: str, start: datetime, end: datetime
    ) -> dict:
        """Aggregate exercise data from activity sessions."""
        from backend.models.person import ActivitySession

        sessions = (
            db.execute(
                select(ActivitySession).where(
                    and_(
                        ActivitySession.person_id == person_id,
                        ActivitySession.activity_type == "exercise",
                        ActivitySession.status == "closed",
                        or_(
                            and_(
                                ActivitySession.opened_at >= start, ActivitySession.opened_at < end
                            ),
                            and_(
                                ActivitySession.closed_at >= start, ActivitySession.closed_at < end
                            ),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )

        session_count = len(sessions)
        total_minutes = sum(s.duration_minutes or 0 for s in sessions)

        return {
            "session_count": session_count,
            "total_minutes": total_minutes,
        }

    def _aggregate_tv(self, db: Session, person_id: str, start: datetime, end: datetime) -> dict:
        """Aggregate TV-watching data from activity sessions.

        No dedicated ``daily_reports`` column exists for this metric; it is
        persisted via ``metadata_json`` and ``get_report`` reads it back
        from there.
        """
        from backend.models.person import ActivitySession

        sessions = (
            db.execute(
                select(ActivitySession).where(
                    and_(
                        ActivitySession.person_id == person_id,
                        ActivitySession.activity_type == "watching_tv",
                        ActivitySession.status == "closed",
                        or_(
                            and_(
                                ActivitySession.opened_at >= start, ActivitySession.opened_at < end
                            ),
                            and_(
                                ActivitySession.closed_at >= start, ActivitySession.closed_at < end
                            ),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )

        session_count = len(sessions)
        total_minutes = sum(s.duration_minutes or 0 for s in sessions)

        return {
            "session_count": session_count,
            "total_minutes": total_minutes,
        }

    async def _aggregate_room_time(self, person_id: str, start: datetime, end: datetime) -> dict:
        """Aggregate time spent in each room from PersonLocationService.

        Backed by ``room_segments`` (M32), not the legacy
        ``PersonLocationHistory`` table. Degrades to an empty distribution
        when CTS is disabled (``person_location_service`` is ``None``).
        """
        if self._person_location is None:
            return {"distribution": {}, "total_minutes": 0}

        segments = await self._person_location.room_segments(person_id, start, end)

        room_minutes: dict[str, int] = {}
        for seg in segments:
            if not seg.room_name:
                continue

            # Compute overlap with the day range. effective_exited_at clamps
            # a still-open segment to min(now, end), same semantics as the
            # legacy exited_at-or-end clamp below for a closed segment.
            entry = max(seg.entered_at, start)
            exit_time = min(seg.effective_exited_at, end)

            overlap_seconds = (exit_time - entry).total_seconds()
            if overlap_seconds > 0:
                minutes = max(1, int(overlap_seconds / 60))
                room_minutes[seg.room_name] = room_minutes.get(seg.room_name, 0) + minutes

        return {
            "distribution": room_minutes,
            "total_minutes": sum(room_minutes.values()),
        }

    def _generate_llm_summary(self, report: dict) -> str | None:
        """Generate prose summary using LLM.

        Placeholder - integration with LLM service to be added in Phase 6.
        """
        # TODO: Integrate with LLM service for prose summary generation
        logger.warning("llm_summary_not_implemented", person_id=report["person_id"])
        return None

    def _get_room_trends(self, person_id: str, date: str, tz_name: str) -> dict | None:
        """Get room trend data from scene analysis service.

        Graceful degradation: returns None if service unavailable.
        """
        if not self._scene_analysis_client:
            return None

        try:
            # TODO: Implement room trend API call
            return None
        except Exception:
            logger.exception("room_trends_fetch_error", person_id=person_id, date=date)
            return None

    def _compute_wellness(self, report: dict) -> tuple[float | None, list[dict]]:
        """Compute wellness score (0-100) and alert flags.

        Uses configurable thresholds from wellness_thresholds.yaml.
        Returns (score, alerts) where alerts is a list of {type, severity, message}.
        """
        alerts: list[dict] = []
        score_components: list[float] = []

        # Sleep score (30 points max)
        sleep = report.get("sleep", {})
        sleep_minutes = sleep.get("total_minutes", 0) or 0
        if 480 <= sleep_minutes <= 720:  # 8-12 hours
            sleep_score = 30
        elif sleep_minutes > 0:
            sleep_score = max(0, 30 - abs(sleep_minutes - 600) / 20)  # Target 10 hours
        else:
            sleep_score = 0
            alerts.append(
                {
                    "type": "sleep_deprivation",
                    "severity": "warning",
                    "message": "No sleep data recorded. Target: 8-12 hours.",
                }
            )
        score_components.append(sleep_score)

        # Medication adherence score (30 points max)
        medication = report.get("medication", {})
        adherence_pct = medication.get("adherence_pct", 0) or 0
        med_score = min(30, adherence_pct * 0.3)
        score_components.append(med_score)

        if adherence_pct < 50:
            alerts.append(
                {
                    "type": "medication_missed",
                    "severity": "critical",
                    "message": f"Low medication adherence: {adherence_pct:.0f}%",
                }
            )

        # Activity score (20 points max)
        exercise = report.get("exercise", {})
        exercise_minutes = exercise.get("total_minutes", 0) or 0
        activity_score = 20 if exercise_minutes >= 30 else max(0, exercise_minutes / 30 * 20)
        score_components.append(activity_score)

        # Bathroom safety score (20 points max)
        bathroom = report.get("bathroom_visits", {})
        visit_count = bathroom.get("visit_count", 0) or 0
        if visit_count > 10:  # Potential incontinence issue
            alerts.append(
                {
                    "type": "bathroom_frequency",
                    "severity": "warning",
                    "message": f"High bathroom visit count: {visit_count}",
                }
            )
        score_components.append(20)  # Base score, no penalty logic yet

        wellness_score = sum(score_components)

        return round(wellness_score, 1), alerts

    def _upsert_report_db(self, db: Session, person_id: str, date: str, report: dict) -> None:
        """Upsert report record in database.

        Ensures the HouseholdMember exists before inserting the DailyReport
        to satisfy foreign key constraints.
        """
        from backend.models.person import (
            DailyReport,
            HouseholdMember,
        )

        report_id = f"{person_id}_{date}"

        # Ensure prerequisite records exist for FK constraints
        person = db.get(HouseholdMember, person_id)
        if not person:
            person = HouseholdMember(id=person_id, name="Unknown", is_active=True)
            db.add(person)

        existing = db.get(DailyReport, report_id)
        if existing:
            # Update existing
            existing.status = "complete"
            existing.generated_at = report["generated_at"]
            # Populate specific columns
            sleep = report.get("sleep", {})
            existing.sleep_total_minutes = sleep.get("total_minutes")
            existing.sleep_quality_score = sleep.get("quality_score")
            existing.sleep_disruptions = sleep.get("disruptions")

            meals = report.get("meals", {})
            existing.meal_prep_count = meals.get("prep_count")
            existing.meal_eating_count = meals.get("eating_count")
            existing.meal_avg_duration_minutes = meals.get("avg_duration_minutes")

            medication = report.get("medication", {})
            existing.medication_doses_taken = medication.get("doses_taken")
            existing.medication_doses_due = medication.get("doses_due")
            existing.medication_adherence_pct = medication.get("adherence_pct")

            bathroom = report.get("bathroom_visits", {})
            existing.bathroom_visit_count = bathroom.get("visit_count")
            existing.bathroom_total_minutes = bathroom.get("total_minutes")

            exercise = report.get("exercise", {})
            existing.exercise_session_count = exercise.get("session_count")
            existing.exercise_total_minutes = exercise.get("total_minutes")

            existing.room_time_json = report.get("room_time", {}).get("distribution")
            existing.summary_text = report.get("summary_text")
            existing.wellness_score = report.get("wellness_score")
            existing.wellness_alerts_json = report.get("wellness_alerts")
            existing.metadata_json = {
                k: _serialize_datetime(v) if isinstance(v, datetime) else v
                for k, v in report.items()
            }
        else:
            # Create new
            sleep = report.get("sleep", {})
            meals = report.get("meals", {})
            medication = report.get("medication", {})
            bathroom = report.get("bathroom_visits", {})
            exercise = report.get("exercise", {})
            room_time = report.get("room_time", {})

            report_record = DailyReport(
                id=report_id,
                person_id=person_id,
                report_date=date,
                status="complete",
                generated_at=report["generated_at"],
                sleep_total_minutes=sleep.get("total_minutes"),
                sleep_quality_score=sleep.get("quality_score"),
                sleep_disruptions=sleep.get("disruptions"),
                meal_prep_count=meals.get("prep_count"),
                meal_eating_count=meals.get("eating_count"),
                meal_avg_duration_minutes=meals.get("avg_duration_minutes"),
                medication_doses_taken=medication.get("doses_taken"),
                medication_doses_due=medication.get("doses_due"),
                medication_adherence_pct=medication.get("adherence_pct"),
                bathroom_visit_count=bathroom.get("visit_count"),
                bathroom_total_minutes=bathroom.get("total_minutes"),
                exercise_session_count=exercise.get("session_count"),
                exercise_total_minutes=exercise.get("total_minutes"),
                room_time_json=room_time.get("distribution"),
                summary_text=report.get("summary_text"),
                wellness_score=report.get("wellness_score"),
                wellness_alerts_json=report.get("wellness_alerts"),
                metadata_json={
                    k: _serialize_datetime(v) if isinstance(v, datetime) else v
                    for k, v in report.items()
                },
            )
            db.add(report_record)

        db.commit()

    def get_report(self, person_id: str, date: str) -> dict | None:
        """Retrieve an existing daily report from database without recomputing it.

        Reconstructed from ``metadata_json``, which ``_upsert_report_db`` always
        sets to the exact dict ``generate_daily_report`` last produced -- this
        keeps the shape identical to the regenerate path (dict-per-metric,
        ``tv``, ``wellness_score``, etc.) instead of hand-rebuilding it from a
        divergent subset of dedicated columns, which is how a prior version of
        this method silently diverged from the BFF router's always-regenerate
        path (returning ``sleep`` as a bare int, omitting ``tv``/``wellness_score``
        entirely).

        Args:
            person_id: Household member ID.
            date: Date string in YYYY-MM-DD format.

        Returns:
            Report dict or None if not found.
        """
        db = self._db_session_factory()
        try:
            from backend.models.person import DailyReport

            report_id = f"{person_id}_{date}"
            record = db.get(DailyReport, report_id)

            if not record:
                return None

            report = dict(record.metadata_json or {})
            report["person_id"] = record.person_id
            report["report_date"] = record.report_date
            report["generated_at"] = record.generated_at
            report.setdefault("tv", {"session_count": 0, "total_minutes": 0})
            return report
        finally:
            db.close()
