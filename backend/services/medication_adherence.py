"""Match logged doses to scheduled ones. Pure: no database, no clock of its own.

A dose counts once. A guided routine and a camera can both log the same dose, so dividing logged
sessions by doses due would overstate adherence and hide a missed dose. Instead each logged dose
fills at most one scheduled slot, the nearest one, and a confirmed dose takes the slot first.

Every logged dose ends in exactly one place: it fills a slot, it is another sighting of a dose
already counted, or it is excess. Excess is a safety matter, because someone with dementia can
forget a dose and take it again. ``MedicationSafetyMonitor`` alerts on it and the daily report
shows it, both from this one classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum
from typing import Any


class DoseStatus(StrEnum):
    TAKEN = "taken"
    """Confirmed step by step in a guided routine."""
    LIKELY_TAKEN = "likely_taken"
    """Inferred from a camera. It counts toward adherence and stays labelled as an inference."""
    MISSED = "missed"
    UPCOMING = "upcoming"
    """Not due yet, or still inside the grace period."""


@dataclass(frozen=True)
class DosePolicy:
    grace_minutes: int = 60
    """How long after its time a dose can still arrive before it counts as missed."""
    match_window_minutes: int = 240
    """How far from a scheduled time a logged dose can be and still fill it."""
    duplicate_window_minutes: int = 30
    """A camera sighting this close to a dose already counted is the same dose."""


def dose_policy_from(settings: Any) -> DosePolicy:
    """Read the ``medication`` section of settings."""
    return DosePolicy(
        grace_minutes=settings.as_int("medication.dose_grace_minutes"),
        match_window_minutes=settings.as_int("medication.dose_match_window_minutes"),
        duplicate_window_minutes=settings.as_int("medication.dose_duplicate_window_minutes"),
    )


@dataclass(frozen=True)
class ScheduledDose:
    entry_id: int
    label: str
    dose_time: time
    due_at: datetime

    @property
    def key(self) -> tuple[int, datetime]:
        """One entry repeats daily, so a slot is the entry on a particular day."""
        return (self.entry_id, self.due_at)


@dataclass(frozen=True)
class LoggedDose:
    at: datetime
    confirmed: bool
    session_id: str = ""


class ExcessKind(StrEnum):
    EXTRA = "extra"
    """Near a scheduled time whose dose was already taken: a possible double dose."""
    UNSCHEDULED = "unscheduled"
    """Not near any scheduled time."""


@dataclass(frozen=True)
class ExcessDose:
    logged: LoggedDose
    kind: ExcessKind
    slot: ScheduledDose | None = None
    """For an extra dose, the scheduled dose it repeats."""


@dataclass(frozen=True)
class DoseClassification:
    filled: dict[tuple[int, datetime], LoggedDose]
    """The logged dose filling each slot, by ``ScheduledDose.key``."""
    excess: list[ExcessDose]


@dataclass(frozen=True)
class ResolvedDose:
    scheduled: ScheduledDose
    status: DoseStatus
    taken_at: datetime | None = None


def _nearest_slots(slots: list[ScheduledDose], logged: LoggedDose) -> list[ScheduledDose]:
    """The slots at the time nearest the logged dose.

    Two medicines due together are two slots. Only that time qualifies: a second log near 8:00
    must not spill into a 9:00 dose and hide that it was missed.
    """
    nearest_due = min((slot.due_at for slot in slots), key=lambda due: abs(due - logged.at))
    return [slot for slot in slots if slot.due_at == nearest_due]


def classify_doses(
    scheduled: list[ScheduledDose],
    logged: list[LoggedDose],
    *,
    policy: DosePolicy,
    tracked_since: datetime | None = None,
) -> DoseClassification:
    """Place every logged dose. Confirmed doses go first, so a camera can never displace one.

    Pass the slots of the days around the one in question: a dose logged at 00:20 belongs to the
    23:30 dose before it. ``tracked_since`` is when the schedule began, because a dose taken
    before then had nothing to exceed.
    """
    slots = sorted(scheduled, key=lambda slot: slot.due_at)
    window = timedelta(minutes=policy.match_window_minutes)
    duplicate_window = timedelta(minutes=policy.duplicate_window_minutes)

    filled: dict[tuple[int, datetime], LoggedDose] = {}
    excess: list[ExcessDose] = []
    counted: list[LoggedDose] = []

    for dose in sorted(logged, key=lambda d: (not d.confirmed, d.at)):
        # Two confirmed doses are two routines, so only a camera sighting can be a repeat.
        if not dose.confirmed and any(abs(d.at - dose.at) <= duplicate_window for d in counted):
            continue

        nearest = _nearest_slots(slots, dose) if slots else []
        in_window = bool(nearest) and abs(nearest[0].due_at - dose.at) <= window
        free = [slot for slot in nearest if slot.key not in filled] if in_window else []
        counted.append(dose)
        if free:
            filled[free[0].key] = dose
        elif tracked_since is None or dose.at >= tracked_since:
            kind = ExcessKind.EXTRA if in_window else ExcessKind.UNSCHEDULED
            excess.append(ExcessDose(dose, kind, nearest[0] if in_window else None))

    return DoseClassification(filled, sorted(excess, key=lambda e: e.logged.at))


def resolve_doses(
    scheduled: list[ScheduledDose],
    classification: DoseClassification,
    *,
    now: datetime,
    policy: DosePolicy,
) -> list[ResolvedDose]:
    """Give every scheduled dose a status, in time order."""
    grace = timedelta(minutes=policy.grace_minutes)
    resolved = []
    for slot in sorted(scheduled, key=lambda s: s.due_at):
        match = classification.filled.get(slot.key)
        if match is not None:
            status = DoseStatus.TAKEN if match.confirmed else DoseStatus.LIKELY_TAKEN
            resolved.append(ResolvedDose(slot, status, match.at))
        elif now >= slot.due_at + grace:
            resolved.append(ResolvedDose(slot, DoseStatus.MISSED))
        else:
            resolved.append(ResolvedDose(slot, DoseStatus.UPCOMING))
    return resolved


def adherence_pct(resolved: list[ResolvedDose]) -> float | None:
    """The share of doses due so far that were taken, or ``None`` when none are due yet."""
    due = [dose for dose in resolved if dose.status is not DoseStatus.UPCOMING]
    if not due:
        return None
    taken = [dose for dose in due if dose.status is not DoseStatus.MISSED]
    return round(len(taken) / len(due) * 100, 1)
