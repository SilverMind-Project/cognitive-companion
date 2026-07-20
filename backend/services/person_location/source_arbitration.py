"""Pure arbitration policy: which source may move an open segment's room (M38).

Mirrors the legacy ``SourceAuthority`` policy
(``backend/services/cts/source_authority.py``), re-expressed in the unified
SSOT's ``SourceTag`` vocabulary. Observation rows are never gated --
:meth:`PersonLocationService.ingest_observation` always inserts the raw row
first; this module only decides whether an incoming observation's *segment*
effect (a room change) is allowed to apply. A same-room observation is a
refresh, not a room change, and never routes through here. ``manual``
overrides bypass this module entirely (``ingest_manual_override`` is
unconditional, as before M38).

Every rule here is a pure function of its inputs so every case is a test
case, matching ``segment_state_machine.decide``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .types import SourceTag

# Priority ranking: higher wins outright. Mirrors
# backend/services/cts/source_authority.py's SOURCE_PRIORITY, minus the
# legacy cts:unknown / ha:correlated split (the SSOT's segment machine
# already refuses to open/move a segment with room_id=None, so an
# "unknown identity" observation never reaches the arbiter with a room to
# contest).
#
# "manual" is not an incoming-event source here (ingest_manual_override
# bypasses this module entirely -- a caregiver override always applies
# immediately), but it is a real *incumbent* value once a manual segment's
# last_source is set: without an entry, an unranked source defaults to
# priority 0 and any subsequent camera/sensor observation of a different
# room would supersede a manual placement instantly, with no staleness
# protection (owner decision 2026-07-19: a caregiver override should not be
# erasable by a single camera glitch). Ranking it above every automatic
# source means an incoming observation must still wait out the staleness
# handoff window, consistent with W9's "manual never ages" intent, while
# stopping short of making it permanently un-overridable.
PRIORITY: dict[SourceTag, int] = {
    "manual": 200,
    "world_tracker": 100,
    "face_sighting": 80,
    "sensor": 40,
}

DEFAULT_ARBITRATION_STALENESS_S = 30.0


@dataclass(frozen=True)
class ArbitrationVerdict:
    allowed: bool
    reason: str


def arbitrate(
    *,
    incoming_source: SourceTag,
    incoming_at: datetime,
    last_evidence_source: SourceTag | None,
    last_evidence_at: datetime | None,
    staleness_s: float = DEFAULT_ARBITRATION_STALENESS_S,
) -> ArbitrationVerdict:
    """Decide whether an incoming observation may change the open segment's room.

    Args:
        incoming_source: The source tag of the incoming observation.
        incoming_at: The incoming observation's ``observed_at``.
        last_evidence_source: The open segment's ``metadata["last_source"]``,
            or ``None`` if the segment has none (opened before M38, or by a
            transit/manual event that predates a same-source observation).
        last_evidence_at: The open segment's ``last_observed_at`` (falling
            back to ``entered_at`` when no observation has refreshed it),
            or ``None`` if the segment has neither.
        staleness_s: Seconds of quiet after which a lower-priority source may
            take over (the "staleness handoff" window).

    Returns:
        An :class:`ArbitrationVerdict`. ``reason`` is one of
        ``"no_prior_evidence"``, ``"out_of_order"``, ``"priority"``,
        ``"stale_handoff"``, or ``"lower_priority_fresh_evidence"``.
    """
    if last_evidence_source is None or last_evidence_at is None:
        return ArbitrationVerdict(True, "no_prior_evidence")

    # Out-of-order guard: a late-arriving observation (e.g. a ~90s-lagged
    # reCamera batch) must never rewrite a segment whose evidence is already
    # newer, regardless of priority. This is what prevents exited_at <
    # entered_at.
    if incoming_at < last_evidence_at:
        return ArbitrationVerdict(False, "out_of_order")

    incoming_priority = PRIORITY.get(incoming_source, 0)
    current_priority = PRIORITY.get(last_evidence_source, 0)

    if incoming_priority >= current_priority:
        return ArbitrationVerdict(True, "priority")

    age_s = (incoming_at - last_evidence_at).total_seconds()
    if age_s > staleness_s:
        return ArbitrationVerdict(True, "stale_handoff")

    return ArbitrationVerdict(False, "lower_priority_fresh_evidence")
