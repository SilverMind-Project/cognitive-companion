"""Alert caregivers to doses beyond the schedule.

Someone with dementia can forget a dose and take it again, so this is a built-in safety check, not
an opt-in rule. Doses arrive by several paths, so it reconciles on a schedule instead of hooking
each one: a new path, or a restart, cannot slip past it.

It works in two passes. ``_detect`` records each excess dose as a ``medication_excess`` signal,
keyed by its session so re-evaluating never repeats one. ``_deliver`` treats those signals as an
outbox: it sends what is due, and writes what it sent into the signal. A crash or a Telegram outage
between the two just means the next tick sends it, and the same step re-sends an alert until a
caregiver acknowledges it or its repeats run out.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.core.time import UTC
from backend.models.medication import MedicationScheduleEntry
from backend.models.person import HouseholdMember
from backend.services.cts.signal_store import SignalStore
from backend.services.medication_adherence import (
    DosePolicy,
    ExcessDose,
    ExcessKind,
    classify_doses,
)
from backend.services.medication_schedule import (
    logged_doses,
    schedule_began_at,
    scheduled_doses,
    scheduled_doses_around,
)

logger = get_logger(__name__)

SIGNAL_KIND = "medication_excess"
LOOKBACK = timedelta(hours=24)


@dataclass(frozen=True)
class EscalationPolicy:
    """How an unacknowledged alert repeats, from ``notification_defaults`` in notifications.yaml."""

    interval_minutes: int = 0
    repeat_count: int = 0


class SignalEmitter(Protocol):
    async def emit(self, **kwargs: Any) -> dict[str, Any]: ...


class Dispatcher(Protocol):
    async def dispatch(
        self, alert_level: str, message: str, room_name: str, rule_config: dict | None = None
    ) -> dict[str, bool]: ...


def severity_for(dose: ExcessDose) -> str:
    """A confirmed dose certainly happened. A camera sighting may not have been one."""
    return "emergency" if dose.logged.confirmed else "warning"


def alert_text(name: str, dose: ExcessDose, tz: ZoneInfo) -> str:
    at = dose.logged.at.astimezone(tz).strftime("%-I:%M %p")
    if dose.kind is ExcessKind.EXTRA and dose.slot is not None:
        taken = f"{dose.slot.label} was already taken."
        if dose.logged.confirmed:
            return f"{name} took an extra dose at {at}. {taken}"
        return f"The camera saw {name} take what may be an extra dose at {at}. {taken}"
    if dose.logged.confirmed:
        return f"{name} took a dose at {at}, when none was scheduled."
    return f"The camera saw {name} take what may be a dose at {at}, when none was scheduled."


class MedicationSafetyMonitor:
    def __init__(
        self,
        db_factory: Callable[[], Session],
        signals: SignalEmitter,
        dispatcher: Dispatcher,
        *,
        tz_name: str,
        channels: Sequence[str],
        dose_policy: DosePolicy,
        escalation: Mapping[str, EscalationPolicy],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._db_factory = db_factory
        self._signals = signals
        self._dispatcher = dispatcher
        self._store = SignalStore(db_factory=db_factory)
        self._tz = ZoneInfo(tz_name)
        self._channels = list(channels)
        self._dose_policy = dose_policy
        self._escalation = escalation
        self._now = now

    async def tick(self) -> None:
        """One pass. Each person and alert stands alone, so one failure cannot block another."""
        now = self._now()
        with self._db_factory() as db:
            people = db.execute(
                select(HouseholdMember.id, HouseholdMember.name)
                .join(
                    MedicationScheduleEntry,
                    MedicationScheduleEntry.person_id == HouseholdMember.id,
                )
                .distinct()
            ).all()
        for person_id, name in people:
            try:
                await self._detect(person_id, name, now)
            except Exception:
                logger.exception("medication_safety_detect_error", person_id=person_id)
        await self._deliver(now)

    def _excess_doses(
        self, db: Session, person_id: str, day: date, now: datetime
    ) -> list[ExcessDose]:
        if scheduled_doses(db, person_id, day, self._tz) is None:
            return []
        # Twice the lookback, so a dose near its start still sees the doses before it.
        classification = classify_doses(
            scheduled_doses_around(db, person_id, day, self._tz),
            logged_doses(db, person_id, now - 2 * LOOKBACK, now + timedelta(minutes=1)),
            policy=self._dose_policy,
            tracked_since=schedule_began_at(db, person_id),
        )
        return [dose for dose in classification.excess if dose.logged.at >= now - LOOKBACK]

    async def _detect(self, person_id: str, name: str, now: datetime) -> None:
        day = now.astimezone(self._tz).date()
        with self._db_factory() as db:
            excess = self._excess_doses(db, person_id, day, now)
        for dose in excess:
            result = await self._signals.emit(
                signal_kind=SIGNAL_KIND,
                person_id=person_id,
                severity=severity_for(dose),
                now=dose.logged.at,
                idempotency_key=dose.logged.session_id,
                context={
                    "summary": alert_text(name, dose, self._tz),
                    "kind": dose.kind.value,
                    "session_id": dose.logged.session_id,
                    "confirmed": dose.logged.confirmed,
                    "notifications_sent": 0,
                    "last_notified_at": None,
                },
            )
            if result["emitted"]:
                logger.warning(
                    "medication_excess_detected",
                    person_id=person_id,
                    kind=dose.kind.value,
                    session_id=dose.logged.session_id,
                )

    def _is_due(self, signal: dict[str, Any], now: datetime) -> bool:
        context = signal.get("context_json") or {}
        sent = context.get("notifications_sent", 0)
        if sent == 0:
            return True
        policy = self._escalation.get(signal["severity"], EscalationPolicy())
        if policy.interval_minutes <= 0 or sent > policy.repeat_count:
            return False
        last = datetime.fromisoformat(context["last_notified_at"])
        return now - last >= timedelta(minutes=policy.interval_minutes)

    async def _deliver(self, now: datetime) -> None:
        for severity in ("emergency", "warning"):
            pending = await self._store.get_unacknowledged(severity=severity, window_hours=24)
            for signal in pending:
                if signal.get("signal_type") == SIGNAL_KIND and self._is_due(signal, now):
                    await self._send(signal, now)

    async def _send(self, signal: dict[str, Any], now: datetime) -> None:
        context = signal.get("context_json") or {}
        try:
            results = await self._dispatcher.dispatch(
                alert_level=signal["severity"],
                message=context["summary"],
                room_name="",
                rule_config={"channels": self._channels},
            )
        except Exception:
            logger.exception("medication_alert_dispatch_error", signal_row_id=signal["id"])
            return
        if not any(results.values()):
            logger.error("medication_alert_undelivered", signal_row_id=signal["id"])
            return  # Nothing was sent, so the next tick tries again.
        await self._store.merge_context(
            signal["id"],
            {
                "notifications_sent": context.get("notifications_sent", 0) + 1,
                "last_notified_at": now.isoformat(),
            },
        )
