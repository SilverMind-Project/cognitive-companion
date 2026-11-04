"""Schedule changes take effect from a dose's next occurrence, and never rewrite history."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from backend.core.exceptions import NotFoundError
from backend.models.medication import MedicationScheduleEntry
from backend.models.person import HouseholdMember
from backend.services.medication_schedule import MedicationScheduleService, scheduled_doses

NY = ZoneInfo("America/New_York")
TODAY = date(2026, 11, 4)  # A Wednesday.
NOON = datetime(2026, 11, 4, 12, 0, tzinfo=NY)


@pytest.fixture(autouse=True)
def _household_in_new_york(monkeypatch):
    from backend.services import medication_schedule

    monkeypatch.setattr(medication_schedule.settings, "as_str", lambda _key: "America/New_York")


@pytest.fixture
def person(db_factory) -> str:
    db = db_factory()
    db.add(HouseholdMember(id="rose", name="Rose"))
    db.commit()
    db.close()
    return "rose"


def service(db_factory, now: datetime = NOON) -> MedicationScheduleService:
    return MedicationScheduleService(db_factory, now=lambda: now.astimezone(UTC))


def rows(db_factory) -> list[MedicationScheduleEntry]:
    db = db_factory()
    try:
        return list(
            db.scalars(select(MedicationScheduleEntry).order_by(MedicationScheduleEntry.id))
        )
    finally:
        db.close()


def due_on(db_factory, person: str, day: date) -> list[time] | None:
    db = db_factory()
    try:
        doses = scheduled_doses(db, person, day, NY)
        return None if doses is None else sorted(d.dose_time for d in doses)
    finally:
        db.close()


def test_a_dose_added_after_its_time_starts_tomorrow(db_factory, person) -> None:
    entry = service(db_factory).create_entry(person, label="Morning", dose_time=time(8))
    assert entry.starts_on == TODAY + timedelta(days=1)
    assert due_on(db_factory, person, TODAY) is None


def test_a_dose_added_before_its_time_starts_today(db_factory, person) -> None:
    entry = service(db_factory).create_entry(person, label="Evening", dose_time=time(20))
    assert entry.starts_on == TODAY
    assert due_on(db_factory, person, TODAY) == [time(20)]


def test_today_follows_the_household_timezone(db_factory, person) -> None:
    """9 PM in New York is already tomorrow in UTC."""
    late = datetime(2026, 11, 4, 21, 0, tzinfo=NY)
    entry = service(db_factory, late).create_entry(person, label="Night", dose_time=time(22))
    assert entry.starts_on == TODAY


def test_days_are_stored_sorted_and_unique(db_factory, person) -> None:
    entry = service(db_factory).create_entry(
        person, label="Weekly", dose_time=time(20), days_of_week=[4, 0, 4]
    )
    assert entry.days_of_week == [0, 4]


def test_a_weekday_dose_is_not_due_on_a_sunday(db_factory, person) -> None:
    service(db_factory).create_entry(
        person, label="Weekdays", dose_time=time(20), days_of_week=[0, 1, 2, 3, 4]
    )
    assert due_on(db_factory, person, date(2026, 11, 8)) == []
    assert due_on(db_factory, person, date(2026, 11, 9)) == [time(20)]


def test_a_person_with_no_schedule_has_none_not_an_empty_day(db_factory, person) -> None:
    assert due_on(db_factory, person, TODAY) is None


def test_dose_time_stays_at_eight_across_daylight_saving(db_factory, person) -> None:
    last_week = NOON - timedelta(days=30)
    service(db_factory, last_week).create_entry(person, label="Morning", dose_time=time(8))
    db = db_factory()
    before = scheduled_doses(db, person, date(2026, 10, 31), NY)[0].due_at
    after = scheduled_doses(db, person, date(2026, 11, 2), NY)[0].due_at
    db.close()
    assert (before.hour, after.hour) == (8, 8)
    assert before.utcoffset() != after.utcoffset()


def test_changing_a_dose_keeps_the_past_as_it_was(db_factory, person) -> None:
    old = service(db_factory, NOON - timedelta(days=10)).create_entry(
        person, label="Morning", dose_time=time(8)
    )
    new = service(db_factory).update_entry(person, old.id, dose_time=time(9))

    assert new.id != old.id
    assert due_on(db_factory, person, TODAY - timedelta(days=3)) == [time(8)]
    assert due_on(db_factory, person, TODAY) == [time(8)]
    assert due_on(db_factory, person, TODAY + timedelta(days=1)) == [time(9)]


def test_a_change_never_doubles_a_dose_on_one_day(db_factory, person) -> None:
    """The 8:00 dose has passed today, so moving it to 20:00 starts tomorrow."""
    old = service(db_factory, NOON - timedelta(days=10)).create_entry(
        person, label="Morning", dose_time=time(8)
    )
    service(db_factory).update_entry(person, old.id, dose_time=time(20))
    assert due_on(db_factory, person, TODAY) == [time(8)]
    assert due_on(db_factory, person, TODAY + timedelta(days=1)) == [time(20)]


def test_changing_a_dose_still_ahead_today_applies_today(db_factory, person) -> None:
    old = service(db_factory, NOON - timedelta(days=10)).create_entry(
        person, label="Evening", dose_time=time(20)
    )
    service(db_factory).update_entry(person, old.id, dose_time=time(21))
    assert due_on(db_factory, person, TODAY) == [time(21)]


def test_changing_only_the_label_keeps_the_rest(db_factory, person) -> None:
    old = service(db_factory, NOON - timedelta(days=10)).create_entry(
        person, label="Tablets", dose_time=time(20), days_of_week=[0, 2]
    )
    new = service(db_factory).update_entry(person, old.id, label="Heart tablets")
    assert (new.label, new.dose_time, new.days_of_week) == ("Heart tablets", time(20), [0, 2])


def test_removing_a_dose_ends_it_after_its_last_occurrence(db_factory, person) -> None:
    old = service(db_factory, NOON - timedelta(days=10)).create_entry(
        person, label="Morning", dose_time=time(8)
    )
    service(db_factory).remove_entry(person, old.id)

    assert due_on(db_factory, person, TODAY) == [time(8)]
    assert due_on(db_factory, person, TODAY + timedelta(days=1)) is None
    assert service(db_factory).list_entries(person) == []


def test_removing_a_dose_that_never_took_effect_leaves_no_trace(db_factory, person) -> None:
    entry = service(db_factory).create_entry(person, label="Morning", dose_time=time(8))
    service(db_factory).remove_entry(person, entry.id)
    assert rows(db_factory) == []


def test_listing_is_in_time_order(db_factory, person) -> None:
    svc = service(db_factory)
    svc.create_entry(person, label="Evening", dose_time=time(20))
    svc.create_entry(person, label="Morning", dose_time=time(8))
    assert [e.label for e in svc.list_entries(person)] == ["Morning", "Evening"]


def test_an_unknown_person_is_not_found(db_factory) -> None:
    with pytest.raises(NotFoundError):
        service(db_factory).list_entries("nobody")


def test_another_persons_entry_is_not_found(db_factory, person) -> None:
    db = db_factory()
    db.add(HouseholdMember(id="david", name="David"))
    db.commit()
    db.close()
    entry = service(db_factory).create_entry(person, label="Morning", dose_time=time(20))
    with pytest.raises(NotFoundError):
        service(db_factory).remove_entry("david", entry.id)


def test_an_ended_entry_cannot_be_changed(db_factory, person) -> None:
    old = service(db_factory, NOON - timedelta(days=10)).create_entry(
        person, label="Morning", dose_time=time(8)
    )
    service(db_factory).remove_entry(person, old.id)
    with pytest.raises(NotFoundError):
        service(db_factory).update_entry(person, old.id, label="Again")
