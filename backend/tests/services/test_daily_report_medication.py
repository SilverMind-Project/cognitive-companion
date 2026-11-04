"""How the daily report reads a medication schedule."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from backend.models.medication import MedicationScheduleEntry
from backend.models.person import (
    ActivitySession,
    ActivitySourceEnum,
    ActivityTypeEnum,
    HouseholdMember,
)
from backend.services.daily_report import DailyReportService

NY = ZoneInfo("America/New_York")
DAY = "2026-11-04"


def local(hour: int, minute: int = 0, day: int = 4) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=NY)


@pytest.fixture
def rose(db_factory) -> str:
    db = db_factory()
    db.add(HouseholdMember(id="rose", name="Rose"))
    db.commit()
    db.close()
    return "rose"


def schedule(db_factory, person: str, *times: str, starts_on: date = date(2020, 1, 1)) -> None:
    db = db_factory()
    for dose_time in times:
        db.add(
            MedicationScheduleEntry(
                person_id=person,
                label=f"Dose at {dose_time}",
                dose_time=time.fromisoformat(dose_time),
                days_of_week=[0, 1, 2, 3, 4, 5, 6],
                starts_on=starts_on,
                created_at=datetime(2020, 1, 1, tzinfo=UTC),
            )
        )
    db.commit()
    db.close()


def log_dose(db_factory, person: str, at: datetime, *, confirmed: bool = False) -> None:
    source = (
        ActivitySourceEnum.guided_companion if confirmed else ActivitySourceEnum.vision_inferred
    )
    db = db_factory()
    db.add(
        ActivitySession(
            id=f"{person}-{at.isoformat()}-{source.value}",
            person_id=person,
            activity_type=ActivityTypeEnum.medication,
            opened_at=at.astimezone(UTC),
            closed_at=at.astimezone(UTC) + timedelta(minutes=2),
            duration_minutes=2,
            status="closed",
            source=source,
        )
    )
    db.commit()
    db.close()


async def report(db_factory, person: str, now: datetime, day: str = DAY) -> dict:
    service = DailyReportService(db_factory, now=lambda: now.astimezone(UTC))
    return await service.generate_daily_report(
        person_id=person, date=day, tz_name="America/New_York"
    )


def med_alerts(result: dict) -> list[dict]:
    return [a for a in result["wellness_alerts"] if a["type"] == "medication_missed"]


async def test_no_schedule_means_nothing_was_due(db_factory, rose) -> None:
    log_dose(db_factory, rose, local(8))
    result = await report(db_factory, rose, local(23))

    medication = result["medication"]
    assert medication["doses_taken"] == 1
    assert medication["doses_due"] is None
    assert medication["adherence_pct"] is None
    assert medication["doses"] == []
    assert med_alerts(result) == []


async def test_no_schedule_does_not_cap_the_wellness_score(db_factory, rose) -> None:
    db = db_factory()
    now = local(23)
    for index, (kind, minutes) in enumerate(
        ((ActivityTypeEnum.sleep, 540), (ActivityTypeEnum.exercise, 45))
    ):
        db.add(
            ActivitySession(
                id=f"session-{index}",
                person_id=rose,
                activity_type=kind,
                opened_at=(now - timedelta(minutes=minutes + 30)).astimezone(UTC),
                closed_at=(now - timedelta(minutes=30)).astimezone(UTC),
                duration_minutes=minutes,
                status="closed",
            )
        )
    db.commit()
    db.close()
    result = await report(db_factory, rose, now)
    assert result["wellness_score"] == 100.0


async def test_a_morning_report_is_not_alarmed_by_the_evening_dose(db_factory, rose) -> None:
    schedule(db_factory, rose, "08:00", "20:00")
    log_dose(db_factory, rose, local(8, 10), confirmed=True)
    result = await report(db_factory, rose, local(9))

    medication = result["medication"]
    assert medication["doses_scheduled"] == 2
    assert medication["doses_due"] == 1
    assert medication["adherence_pct"] == 100.0
    assert [d["status"] for d in medication["doses"]] == ["taken", "upcoming"]


async def test_a_dose_inside_the_grace_period_raises_no_alert(db_factory, rose) -> None:
    schedule(db_factory, rose, "08:00")
    result = await report(db_factory, rose, local(8, 5))
    assert result["medication"]["adherence_pct"] is None
    assert med_alerts(result) == []


async def test_a_missed_dose_alerts_with_the_real_counts(db_factory, rose) -> None:
    schedule(db_factory, rose, "08:00", "20:00")
    result = await report(db_factory, rose, local(23))
    assert result["medication"]["adherence_pct"] == 0.0
    assert med_alerts(result)[0]["message"] == "Missed 2 of 2 doses due"


async def test_two_daily_doses_taken_are_full_adherence(db_factory, rose) -> None:
    """The placeholder assumed three doses, which read this as 67%."""
    schedule(db_factory, rose, "08:00", "20:00")
    log_dose(db_factory, rose, local(8, 5), confirmed=True)
    log_dose(db_factory, rose, local(20, 5), confirmed=True)
    result = await report(db_factory, rose, local(23))
    assert result["medication"]["adherence_pct"] == 100.0
    assert med_alerts(result) == []


async def test_camera_doses_count_and_stay_labelled(db_factory, rose) -> None:
    schedule(db_factory, rose, "08:00")
    log_dose(db_factory, rose, local(8, 10), confirmed=False)
    result = await report(db_factory, rose, local(23))

    medication = result["medication"]
    assert medication["doses"][0]["status"] == "likely_taken"
    assert medication["adherence_pct"] == 100.0
    assert (medication["confirmed_doses"], medication["inferred_doses"]) == (0, 1)
    assert med_alerts(result) == []


async def test_one_dose_seen_twice_cannot_hide_a_missed_dose(db_factory, rose) -> None:
    schedule(db_factory, rose, "08:00", "20:00")
    log_dose(db_factory, rose, local(8, 5), confirmed=True)
    log_dose(db_factory, rose, local(8, 6), confirmed=False)
    result = await report(db_factory, rose, local(23))

    medication = result["medication"]
    assert medication["doses_taken"] == 2
    assert medication["doses_missed"] == 1
    assert medication["adherence_pct"] == 50.0


async def test_a_late_night_dose_logged_after_midnight_still_counts(db_factory, rose) -> None:
    schedule(db_factory, rose, "23:30")
    log_dose(db_factory, rose, local(0, 20, day=5), confirmed=True)
    result = await report(db_factory, rose, local(9, day=5))
    assert result["medication"]["doses"][0]["status"] == "taken"
    assert result["medication"]["doses_taken"] == 0


async def test_an_extra_dose_shows_in_the_report_and_raises_an_alert(db_factory, rose) -> None:
    schedule(db_factory, rose, "08:00")
    log_dose(db_factory, rose, local(8, 5), confirmed=True)
    log_dose(db_factory, rose, local(9, 30), confirmed=True)
    result = await report(db_factory, rose, local(23))

    medication = result["medication"]
    assert medication["doses_excess"] == 1
    assert medication["excess_doses"][0]["kind"] == "extra"
    assert medication["excess_doses"][0]["repeats"] == "Dose at 08:00"
    assert medication["adherence_pct"] == 100.0
    alert = next(a for a in result["wellness_alerts"] if a["type"] == "medication_excess")
    assert alert["severity"] == "critical"


async def test_a_dose_taken_before_the_schedule_existed_is_not_excess(db_factory, rose) -> None:
    db = db_factory()
    db.add(
        MedicationScheduleEntry(
            person_id=rose,
            label="Evening",
            dose_time=time(20),
            days_of_week=[0, 1, 2, 3, 4, 5, 6],
            starts_on=date(2026, 11, 4),
            created_at=local(12).astimezone(UTC),
        )
    )
    db.commit()
    db.close()
    log_dose(db_factory, rose, local(8), confirmed=True)
    result = await report(db_factory, rose, local(13))
    assert result["medication"]["doses_excess"] == 0


async def test_a_past_day_counts_every_dose(db_factory, rose) -> None:
    schedule(db_factory, rose, "08:00", "20:00")
    result = await report(db_factory, rose, local(9, day=10))
    assert result["medication"]["doses_due"] == 2


async def test_a_day_before_the_schedule_began_has_nothing_due(db_factory, rose) -> None:
    schedule(db_factory, rose, "08:00", starts_on=date(2026, 11, 5))
    result = await report(db_factory, rose, local(23))
    assert result["medication"]["doses_due"] is None


async def test_the_stored_report_keeps_each_dose(db_factory, rose) -> None:
    schedule(db_factory, rose, "08:00")
    log_dose(db_factory, rose, local(8, 5), confirmed=True)
    await report(db_factory, rose, local(23))
    stored = DailyReportService(db_factory).get_report(person_id=rose, date=DAY)
    assert stored["medication"]["doses"][0]["dose_time"] == "08:00"
