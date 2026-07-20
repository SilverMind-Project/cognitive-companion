"""M38 Part F: source_arbitration.arbitrate() pure unit suite.

Every priority pair crossed with fresh/stale segment evidence, the
out-of-order guard, and the no-prior-evidence bootstrap case.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.services.person_location.source_arbitration import (
    DEFAULT_ARBITRATION_STALENESS_S,
    arbitrate,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def test_no_prior_evidence_always_allowed():
    verdict = arbitrate(
        incoming_source="sensor",
        incoming_at=T0,
        last_evidence_source=None,
        last_evidence_at=None,
    )
    assert verdict.allowed
    assert verdict.reason == "no_prior_evidence"


def test_out_of_order_incoming_rejected_regardless_of_priority():
    """A world_tracker event predating the current evidence is still rejected."""
    verdict = arbitrate(
        incoming_source="world_tracker",
        incoming_at=T0 - timedelta(seconds=1),
        last_evidence_source="sensor",
        last_evidence_at=T0,
    )
    assert not verdict.allowed
    assert verdict.reason == "out_of_order"


def test_higher_priority_wins_immediately():
    verdict = arbitrate(
        incoming_source="world_tracker",
        incoming_at=T0 + timedelta(seconds=1),
        last_evidence_source="sensor",
        last_evidence_at=T0,
    )
    assert verdict.allowed
    assert verdict.reason == "priority"


def test_equal_priority_wins_immediately():
    verdict = arbitrate(
        incoming_source="face_sighting",
        incoming_at=T0 + timedelta(seconds=1),
        last_evidence_source="face_sighting",
        last_evidence_at=T0,
    )
    assert verdict.allowed
    assert verdict.reason == "priority"


def test_lower_priority_blocked_while_evidence_fresh():
    verdict = arbitrate(
        incoming_source="sensor",
        incoming_at=T0 + timedelta(seconds=5),
        last_evidence_source="world_tracker",
        last_evidence_at=T0,
        staleness_s=DEFAULT_ARBITRATION_STALENESS_S,
    )
    assert not verdict.allowed
    assert verdict.reason == "lower_priority_fresh_evidence"


def test_lower_priority_allowed_after_staleness_handoff():
    verdict = arbitrate(
        incoming_source="sensor",
        incoming_at=T0 + timedelta(seconds=DEFAULT_ARBITRATION_STALENESS_S + 1),
        last_evidence_source="world_tracker",
        last_evidence_at=T0,
        staleness_s=DEFAULT_ARBITRATION_STALENESS_S,
    )
    assert verdict.allowed
    assert verdict.reason == "stale_handoff"


def test_lower_priority_at_exact_staleness_boundary_still_blocked():
    """age_s > staleness_s (strict), so exactly-at-boundary is still blocked."""
    verdict = arbitrate(
        incoming_source="sensor",
        incoming_at=T0 + timedelta(seconds=DEFAULT_ARBITRATION_STALENESS_S),
        last_evidence_source="world_tracker",
        last_evidence_at=T0,
        staleness_s=DEFAULT_ARBITRATION_STALENESS_S,
    )
    assert not verdict.allowed
    assert verdict.reason == "lower_priority_fresh_evidence"


def test_manual_incumbent_outranks_every_automatic_source():
    """Owner decision 2026-07-19: manual is highest priority, not un-overridable.

    A fresh camera/sensor observation must not instantly erase a caregiver's
    manual placement; it must wait out the staleness handoff like any
    lower-priority source would against a higher one.
    """
    for source in ("world_tracker", "face_sighting", "sensor"):
        fresh = arbitrate(
            incoming_source=source,
            incoming_at=T0 + timedelta(seconds=5),
            last_evidence_source="manual",
            last_evidence_at=T0,
        )
        assert not fresh.allowed, f"{source} must not instantly override a fresh manual placement"
        assert fresh.reason == "lower_priority_fresh_evidence"

        stale = arbitrate(
            incoming_source=source,
            incoming_at=T0 + timedelta(seconds=DEFAULT_ARBITRATION_STALENESS_S + 1),
            last_evidence_source="manual",
            last_evidence_at=T0,
        )
        assert stale.allowed, f"{source} must be able to take over a stale manual placement"
        assert stale.reason == "stale_handoff"


def test_unranked_incoming_source_defaults_to_priority_zero():
    """An incoming source absent from PRIORITY (defensive: should not occur in
    practice) is treated as lowest priority, same as the legacy default."""
    verdict = arbitrate(
        incoming_source="__unknown__",  # type: ignore[arg-type]
        incoming_at=T0 + timedelta(seconds=1),
        last_evidence_source="world_tracker",
        last_evidence_at=T0,
    )
    assert not verdict.allowed
    assert verdict.reason == "lower_priority_fresh_evidence"
