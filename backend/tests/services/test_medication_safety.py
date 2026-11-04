"""The excess-dose monitor: one alert per dose, delivered reliably, until someone responds."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from backend.models.cts_signal import DementiaSignal
from backend.models.medication import MedicationScheduleEntry
from backend.models.person import (
    ActivitySession,
    ActivitySourceEnum,
    ActivityTypeEnum,
    HouseholdMember,
)
from backend.services.cts.signal_store import SignalStore
from backend.services.medication_adherence import DosePolicy
from backend.services.medication_safety import EscalationPolicy, MedicationSafetyMonitor
from backend.services.signals import SignalsService

TZ_NAME = "America/New_York"
NY = ZoneInfo(TZ_NAME)
ESCALATION = {
    "emergency": EscalationPolicy(interval_minutes=5, repeat_count=3),
    "warning": EscalationPolicy(interval_minutes=10, repeat_count=3),
}


def local(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 4, hour, minute, tzinfo=NY)


class FakeDispatcher:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.delivers = True

    async def dispatch(self, alert_level, message, room_name, rule_config=None):
        if self.delivers:
            self.sent.append(
                {"level": alert_level, "message": message, "channels": rule_config["channels"]}
            )
        return {"telegram": self.delivers}


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at.astimezone(UTC)


@pytest.fixture
def clock() -> Clock:
    return Clock(local(14))


@pytest.fixture
def dispatcher() -> FakeDispatcher:
    return FakeDispatcher()


@pytest.fixture
def monitor(db_factory, dispatcher, clock) -> MedicationSafetyMonitor:
    return MedicationSafetyMonitor(
        db_factory,
        SignalsService(db_factory),
        dispatcher,
        tz_name=TZ_NAME,
        channels=["telegram"],
        dose_policy=DosePolicy(),
        escalation=ESCALATION,
        now=clock,
    )


@pytest.fixture
def rose(db_factory) -> str:
    db = db_factory()
    db.add(HouseholdMember(id="rose", name="Rose"))
    db.commit()
    db.close()
    return "rose"


def schedule(db_factory, person: str, *times: str) -> None:
    db = db_factory()
    for dose_time in times:
        db.add(
            MedicationScheduleEntry(
                person_id=person,
                label=f"The {dose_time} dose",
                dose_time=time.fromisoformat(dose_time),
                days_of_week=[0, 1, 2, 3, 4, 5, 6],
                starts_on=date(2020, 1, 1),
                created_at=datetime(2020, 1, 1, tzinfo=UTC),
            )
        )
    db.commit()
    db.close()


def log_dose(
    db_factory, person: str, at: datetime, *, confirmed: bool = True, status: str = "closed"
) -> None:
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
            closed_at=at.astimezone(UTC) + timedelta(minutes=2) if status == "closed" else None,
            duration_minutes=2 if status == "closed" else None,
            status=status,
            source=source,
        )
    )
    db.commit()
    db.close()


def signals(db_factory) -> list[DementiaSignal]:
    db = db_factory()
    try:
        return list(db.scalars(select(DementiaSignal).order_by(DementiaSignal.window_start)))
    finally:
        db.close()


async def test_a_dose_on_schedule_raises_nothing(db_factory, rose, monitor, dispatcher) -> None:
    schedule(db_factory, rose, "08:00")
    log_dose(db_factory, rose, local(8, 5))
    await monitor.tick()
    assert signals(db_factory) == []
    assert dispatcher.sent == []


async def test_a_confirmed_double_dose_is_an_emergency(
    db_factory, rose, monitor, dispatcher
) -> None:
    schedule(db_factory, rose, "08:00")
    log_dose(db_factory, rose, local(8, 5))
    log_dose(db_factory, rose, local(9, 10))
    await monitor.tick()

    (signal,) = signals(db_factory)
    assert (signal.signal_type, signal.severity) == ("medication_excess", "emergency")
    assert signal.context_json["kind"] == "extra"
    assert dispatcher.sent == [
        {
            "level": "emergency",
            "message": "Rose took an extra dose at 9:10 AM. The 08:00 dose was already taken.",
            "channels": ["telegram"],
        }
    ]


async def test_a_camera_only_extra_dose_is_a_warning(db_factory, rose, monitor, dispatcher) -> None:
    schedule(db_factory, rose, "08:00")
    log_dose(db_factory, rose, local(8, 5))
    log_dose(db_factory, rose, local(9, 10), confirmed=False)
    await monitor.tick()
    assert dispatcher.sent[0]["level"] == "warning"
    assert dispatcher.sent[0]["message"].startswith("The camera saw Rose take what may be")


async def test_a_dose_with_none_scheduled_near_it_alerts(
    db_factory, rose, monitor, dispatcher
) -> None:
    schedule(db_factory, rose, "08:00", "20:00")
    log_dose(db_factory, rose, local(8))
    log_dose(db_factory, rose, local(13, 30))
    await monitor.tick()
    assert dispatcher.sent[0]["message"] == "Rose took a dose at 1:30 PM, when none was scheduled."


async def test_an_open_session_alerts_without_waiting_for_it_to_close(
    db_factory, rose, monitor, dispatcher
) -> None:
    schedule(db_factory, rose, "08:00")
    log_dose(db_factory, rose, local(8))
    log_dose(db_factory, rose, local(9), confirmed=False, status="open")
    await monitor.tick()
    assert len(dispatcher.sent) == 1


async def test_no_schedule_means_no_alert(db_factory, rose, monitor, dispatcher) -> None:
    log_dose(db_factory, rose, local(8))
    log_dose(db_factory, rose, local(9))
    await monitor.tick()
    assert dispatcher.sent == []


async def test_a_camera_seeing_the_same_dose_is_not_an_alert(
    db_factory, rose, monitor, dispatcher
) -> None:
    schedule(db_factory, rose, "08:00")
    log_dose(db_factory, rose, local(8, 5))
    log_dose(db_factory, rose, local(8, 15), confirmed=False)
    await monitor.tick()
    assert dispatcher.sent == []


async def test_a_dose_just_after_midnight_belongs_to_the_night_before(
    db_factory, rose, monitor, dispatcher, clock
) -> None:
    schedule(db_factory, rose, "23:30")
    clock.at = datetime(2026, 11, 5, 0, 30, tzinfo=NY)
    log_dose(db_factory, rose, datetime(2026, 11, 5, 0, 20, tzinfo=NY))
    await monitor.tick()
    assert dispatcher.sent == []


async def test_ticking_again_never_repeats_a_detection(
    db_factory, rose, monitor, dispatcher
) -> None:
    schedule(db_factory, rose, "08:00")
    log_dose(db_factory, rose, local(8))
    log_dose(db_factory, rose, local(9))
    await monitor.tick()
    await monitor.tick()
    assert len(signals(db_factory)) == 1
    assert len(dispatcher.sent) == 1


async def test_a_second_extra_dose_inside_the_hour_still_alerts(
    db_factory, rose, monitor, dispatcher
) -> None:
    """The time-based dedup would hide this, and it is the worst case."""
    schedule(db_factory, rose, "08:00")
    log_dose(db_factory, rose, local(8))
    log_dose(db_factory, rose, local(9))
    await monitor.tick()
    log_dose(db_factory, rose, local(9, 20))
    await monitor.tick()
    assert len(signals(db_factory)) == 2


async def test_a_restart_does_not_repeat_or_lose_an_alert(
    db_factory, rose, monitor, dispatcher, clock
) -> None:
    schedule(db_factory, rose, "08:00")
    log_dose(db_factory, rose, local(8))
    log_dose(db_factory, rose, local(9))
    await monitor.tick()
    restarted = MedicationSafetyMonitor(
        db_factory,
        SignalsService(db_factory),
        dispatcher,
        tz_name=TZ_NAME,
        channels=["telegram"],
        dose_policy=DosePolicy(),
        escalation=ESCALATION,
        now=clock,
    )
    await restarted.tick()
    assert len(dispatcher.sent) == 1


async def test_an_outage_retries_until_the_alert_is_delivered(
    db_factory, rose, monitor, dispatcher
) -> None:
    schedule(db_factory, rose, "08:00")
    log_dose(db_factory, rose, local(8))
    log_dose(db_factory, rose, local(9))
    dispatcher.delivers = False
    await monitor.tick()
    assert signals(db_factory)[0].context_json["notifications_sent"] == 0

    dispatcher.delivers = True
    await monitor.tick()
    assert len(dispatcher.sent) == 1


async def test_it_resends_at_the_interval_then_stops(
    db_factory, rose, monitor, dispatcher, clock
) -> None:
    schedule(db_factory, rose, "08:00")
    log_dose(db_factory, rose, local(8))
    log_dose(db_factory, rose, local(9))
    await monitor.tick()

    clock.at += timedelta(minutes=4)
    await monitor.tick()
    assert len(dispatcher.sent) == 1  # Not yet.

    for _ in range(6):
        clock.at += timedelta(minutes=5)
        await monitor.tick()
    assert len(dispatcher.sent) == 4  # The first send and three repeats.


async def test_acknowledging_stops_the_resends(
    db_factory, rose, monitor, dispatcher, clock
) -> None:
    schedule(db_factory, rose, "08:00")
    log_dose(db_factory, rose, local(8))
    log_dose(db_factory, rose, local(9))
    await monitor.tick()

    await SignalStore(db_factory=db_factory).acknowledge(signals(db_factory)[0].id)
    clock.at += timedelta(minutes=30)
    await monitor.tick()
    assert len(dispatcher.sent) == 1


async def test_one_persons_failure_does_not_stop_the_next(
    db_factory, rose, monitor, dispatcher, monkeypatch
) -> None:
    db = db_factory()
    db.add(HouseholdMember(id="alan", name="Alan"))
    db.commit()
    db.close()
    schedule(db_factory, "alan", "08:00")
    schedule(db_factory, rose, "08:00")
    for person in ("alan", rose):
        log_dose(db_factory, person, local(8))
        log_dose(db_factory, person, local(9))

    real_detect = monitor._detect

    async def flaky(person_id, name, now):
        if person_id == "alan":
            raise RuntimeError("boom")
        await real_detect(person_id, name, now)

    monkeypatch.setattr(monitor, "_detect", flaky)
    await monitor.tick()
    assert [s.person_id for s in signals(db_factory)] == [rose]
