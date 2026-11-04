"""Matching logged doses to the schedule. Pure: no database, no real clock."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from backend.services.medication_adherence import (
    DosePolicy,
    DoseStatus,
    ExcessKind,
    LoggedDose,
    ScheduledDose,
    adherence_pct,
    classify_doses,
    resolve_doses,
)

DAY = datetime(2026, 11, 4, tzinfo=UTC)
POLICY = DosePolicy(grace_minutes=60, match_window_minutes=240, duplicate_window_minutes=30)
END_OF_DAY = DAY + timedelta(hours=23, minutes=59)


def at(hour: int, minute: int = 0) -> datetime:
    return DAY + timedelta(hours=hour, minutes=minute)


def slot(entry_id: int, hour: int, minute: int = 0) -> ScheduledDose:
    return ScheduledDose(entry_id, f"Dose {entry_id}", time(hour, minute), at(hour, minute))


def resolve(scheduled, logged, now=END_OF_DAY):
    classification = classify_doses(scheduled, logged, policy=POLICY)
    return resolve_doses(scheduled, classification, now=now, policy=POLICY)


def statuses(scheduled, logged, now=END_OF_DAY):
    return [dose.status for dose in resolve(scheduled, logged, now)]


def excess(scheduled, logged, **kwargs):
    return classify_doses(scheduled, logged, policy=POLICY, **kwargs).excess


def test_a_confirmed_dose_is_taken() -> None:
    logged = [LoggedDose(at(8, 20), confirmed=True)]
    assert statuses([slot(1, 8)], logged) == [DoseStatus.TAKEN]


def test_a_camera_dose_is_likely_taken_and_still_counts() -> None:
    resolved = resolve([slot(1, 8)], [LoggedDose(at(8, 5), confirmed=False)])
    assert resolved[0].status is DoseStatus.LIKELY_TAKEN
    assert adherence_pct(resolved) == 100.0


def test_nothing_logged_after_the_grace_period_is_missed() -> None:
    assert statuses([slot(1, 8)], [], now=at(9, 0)) == [DoseStatus.MISSED]


def test_nothing_logged_inside_the_grace_period_is_not_missed_yet() -> None:
    assert statuses([slot(1, 8)], [], now=at(8, 59)) == [DoseStatus.UPCOMING]


def test_a_later_dose_is_not_due_yet() -> None:
    resolved = resolve(
        [slot(1, 8), slot(2, 20)], [LoggedDose(at(8, 10), confirmed=True)], now=at(12)
    )
    assert [d.status for d in resolved] == [DoseStatus.TAKEN, DoseStatus.UPCOMING]
    assert adherence_pct(resolved) == 100.0


def test_one_dose_logged_twice_does_not_hide_a_missed_dose() -> None:
    """A routine and a camera both saw the morning dose; the evening dose never happened."""
    logged = [LoggedDose(at(8, 5), confirmed=True), LoggedDose(at(8, 10), confirmed=False)]
    resolved = resolve([slot(1, 8), slot(2, 20)], logged)
    assert [d.status for d in resolved] == [DoseStatus.TAKEN, DoseStatus.MISSED]
    assert adherence_pct(resolved) == 50.0


def test_a_duplicate_log_cannot_spill_into_the_next_dose() -> None:
    logged = [LoggedDose(at(8, 0), confirmed=True), LoggedDose(at(8, 15), confirmed=False)]
    assert statuses([slot(1, 8), slot(2, 9)], logged) == [DoseStatus.TAKEN, DoseStatus.MISSED]


def test_a_sighting_between_two_close_doses_cannot_fill_the_second() -> None:
    """Doses at 8:00 and 8:30. A camera at 8:20 is nearer 8:30, but it saw the 8:05 dose."""
    logged = [LoggedDose(at(8, 5), confirmed=True), LoggedDose(at(8, 20), confirmed=False)]
    scheduled = [slot(1, 8), slot(2, 8, 30)]
    assert statuses(scheduled, logged) == [DoseStatus.TAKEN, DoseStatus.MISSED]
    assert excess(scheduled, logged) == []


def test_a_repeat_sighting_is_one_dose_not_an_extra_one() -> None:
    logged = [LoggedDose(at(8, 5), confirmed=True), LoggedDose(at(8, 10), confirmed=False)]
    assert excess([slot(1, 8)], logged) == []


def test_a_second_confirmed_dose_is_extra_however_soon() -> None:
    """Two routines are two doses. Forgetting and repeating is the case that matters most."""
    second = LoggedDose(at(8, 10), confirmed=True, session_id="second")
    found = excess([slot(1, 8)], [LoggedDose(at(8, 0), confirmed=True), second])
    assert [(e.logged, e.kind, e.slot.entry_id) for e in found] == [(second, ExcessKind.EXTRA, 1)]


def test_a_later_sighting_of_a_taken_dose_is_extra() -> None:
    logged = [LoggedDose(at(8, 0), confirmed=True), LoggedDose(at(9, 0), confirmed=False)]
    assert [e.kind for e in excess([slot(1, 8)], logged)] == [ExcessKind.EXTRA]


def test_a_dose_far_from_any_slot_is_unscheduled() -> None:
    found = excess([slot(1, 8), slot(2, 20)], [LoggedDose(at(14), confirmed=False)])
    assert [(e.kind, e.slot) for e in found] == [(ExcessKind.UNSCHEDULED, None)]


def test_a_dose_on_a_day_with_nothing_scheduled_is_unscheduled() -> None:
    assert [e.kind for e in excess([], [LoggedDose(at(8), confirmed=True)])] == [
        ExcessKind.UNSCHEDULED
    ]


def test_a_dose_before_the_schedule_began_is_not_excess() -> None:
    logged = [LoggedDose(at(7), confirmed=True)]
    assert excess([slot(1, 20)], logged, tracked_since=at(12)) == []


def test_every_extra_dose_is_reported_not_only_the_first() -> None:
    logged = [
        LoggedDose(at(8), confirmed=True),
        LoggedDose(at(9), confirmed=True),
        LoggedDose(at(10), confirmed=True),
    ]
    assert len(excess([slot(1, 8)], logged)) == 2


def test_the_same_entry_on_two_days_is_two_slots() -> None:
    today = ScheduledDose(1, "Night", time(23, 30), at(23, 30))
    tomorrow = ScheduledDose(1, "Night", time(23, 30), at(23, 30) + timedelta(days=1))
    logged = [
        LoggedDose(at(23, 40), confirmed=True),
        LoggedDose(at(23, 40) + timedelta(days=1), confirmed=True),
    ]
    assert excess([today, tomorrow], logged) == []


def test_a_confirmed_dose_wins_the_slot_whatever_the_order() -> None:
    logged = [LoggedDose(at(7, 55), confirmed=False), LoggedDose(at(8, 30), confirmed=True)]
    resolved = resolve([slot(1, 8)], logged)
    assert resolved[0].status is DoseStatus.TAKEN
    assert resolved[0].taken_at == at(8, 30)


def test_two_medicines_at_the_same_time_are_two_doses() -> None:
    logged = [LoggedDose(at(8, 0), confirmed=True), LoggedDose(at(8, 5), confirmed=True)]
    assert statuses([slot(1, 8), slot(2, 8)], logged) == [DoseStatus.TAKEN, DoseStatus.TAKEN]


def test_a_dose_outside_the_window_fills_nothing() -> None:
    logged = [LoggedDose(at(14), confirmed=True)]
    assert statuses([slot(1, 8)], logged) == [DoseStatus.MISSED]


def test_a_late_dose_inside_the_window_still_counts() -> None:
    assert statuses([slot(1, 8)], [LoggedDose(at(11, 30), confirmed=True)]) == [DoseStatus.TAKEN]


def test_no_doses_due_means_no_adherence() -> None:
    assert adherence_pct([]) is None
    resolved = resolve([slot(1, 20)], [], now=at(8))
    assert adherence_pct(resolved) is None
