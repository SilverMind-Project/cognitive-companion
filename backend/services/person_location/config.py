"""Configuration for the unified person location service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonLocationConfig:
    inferred_dwell_max_s: float = 14400.0  # 4 hours
    revision_horizon_s: float = 600.0  # 10 minutes
    ph_anchor_match_distance_m: float = 1.5
    ph_anchor_match_window_s: float = 3.0
    presence_grace_s: float = 30.0  # "away" after 30s of no segment
    # M38: seconds of quiet on the open segment's current source before a
    # lower-priority source may take over (source_arbitration.arbitrate's
    # staleness handoff). Mirrors the legacy SourceAuthority's
    # STALENESS_THRESHOLD_S.
    arbitration_staleness_s: float = 30.0

    # M38 Part C: per-source quiet gaps for *observed* open segments (an
    # inferred segment keeps using inferred_dwell_max_s above). A dense
    # source ages out fast (person left camera coverage); a sparse,
    # rule-driven source stays credible for much longer since its next
    # sighting may be tens of minutes away by design, not by failure.
    # Operator-tunable via settings.yaml's person_location section.
    quiet_gap_world_tracker_s: float = 300.0  # 5 minutes
    quiet_gap_recamera_vlm_s: float = 2700.0  # 45 minutes
    quiet_gap_sensor_s: float = 1800.0  # 30 minutes

    def quiet_gap_s(self, source: str | None) -> float | None:
        """Per-source quiet gap for observed-segment aging, or ``None`` if exempt.

        ``None`` covers ``manual`` (never ages, per the caregiver-override
        contract) and any segment with no recorded ``last_source`` (opened
        before M38, or by a code path that never set one) -- left alone
        rather than guessed at.
        """
        return {
            "world_tracker": self.quiet_gap_world_tracker_s,
            "recamera_vlm": self.quiet_gap_recamera_vlm_s,
            "sensor": self.quiet_gap_sensor_s,
        }.get(source or "")
