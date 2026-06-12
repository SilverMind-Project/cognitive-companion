"""N7: Deterministic plain-language narratives for dementia signals.

Each template produces a reproducible, human-readable explanation
of why a signal fired. No LLM — pure string interpolation.
"""

from __future__ import annotations


def narrative_for(
    kind: str,
    *,
    room_name: str = "",
    threshold_min: int = 0,
    actual_min: float = 0.0,
    entered_at: str = "",
    dwell_seconds: float = 0.0,
    window_start: str = "",
    window_end: str = "",
    transition_count: int = 0,
) -> str:
    """Return a plain-language explanation for the given signal kind."""

    if kind == "bathroom_dwell_anomaly":
        return (
            f"Extended bathroom dwell of {actual_min:.0f} minutes detected "
            f"in {room_name or 'the bathroom'}, entered at {entered_at or 'unknown time'}. "
            f"This exceeds the typical dwell baseline for this person."
        )

    if kind == "inferred_dwell_exceeded":
        return (
            f"Inferred dwell in {room_name or 'a camera-blind room'} exceeded "
            f"{threshold_min or 0} minutes (actual: {actual_min:.0f} min). "
            f"Last observed in {room_name or 'this room'} at {entered_at or 'unknown time'}; "
            f"no contradicting observation since."
        )

    if kind == "presumed_location_unknown":
        return (
            f"Presumed location unknown since {entered_at or 'last observation'}. "
            f"No camera or sensor has confirmed this person's location for "
            f"over {actual_min:.0f} minutes."
        )

    if kind == "identity_disagreement":
        return (
            f"Identity resolver detected conflicting evidence for this person "
            f"during the window {window_start or 'start'} to {window_end or 'end'}. "
            f"Multiple identity candidates were proposed with similar probabilities."
        )

    if kind == "pacing":
        return (
            f"Pacing behaviour detected: {transition_count or 'multiple'} room transitions "
            f"within a {int(actual_min) if actual_min > 0 else ''} minute window "
            f"from {window_start or 'start'} to {window_end or 'end'}. "
            f"This may indicate agitation or restlessness."
        )

    if kind == "stillness_anomaly":
        return (
            f"Stillness anomaly: person remained stationary for {actual_min:.0f} minutes "
            f"in {room_name or 'an unknown room'}. "
            f"Motion energy was below the detection threshold throughout the period "
            f"from {window_start or 'start'} to {window_end or 'end'}."
        )

    if kind == "nighttime_movement":
        return (
            f"Nighttime movement detected: {transition_count or 'several'} transitions "
            f"during nighttime hours ({window_start or 'late night'} to {window_end or 'early morning'}). "
            f"This may indicate disrupted sleep."
        )

    if kind == "sundowning_index":
        return (
            f"Sundowning indicator elevated during the evening window "
            f"{window_start or 'late afternoon'} to {window_end or 'evening'}. "
            f"Increased activity and transitions observed during this period."
        )

    if kind == "absence":
        return (
            f"Absence detected: no observations of this person for "
            f"{actual_min:.0f} minutes since {entered_at or 'last seen'}. "
            f"This exceeds the configured absence threshold."
        )

    if kind == "gait_slowing":
        return (
            f"Gait slowing detected: walking speed over the last 28 days "
            f"({actual_min:.2f} m/s) is meaningfully lower than the prior 28-day baseline "
            f"({threshold_min / 100:.2f} m/s). "
            f"Sustained gait speed decline is a validated early indicator of cognitive decline. "
            f"This is a trend signal, not an acute alert."
        )

    if kind == "agitation_index":
        return (
            f"Restlessness elevated: the agitation motor index ({actual_min:.2f}) "
            f"is meaningfully above this person's personal baseline. "
            f"The index combines in-place body motion, aimless direction changes, "
            f"and short repetitive sub-room excursions over the last 30 minutes. "
            f"This is an experimental signal; validate with caregiver observation before acting."
        )

    if kind == "fall_suspected":
        return (
            f"Possible fall detected in {room_name or 'an unknown room'} "
            f"at {entered_at or window_start or 'unknown time'}. "
            f"Sudden vertical collapse and post-event stillness were detected by the fall fast path. "
            f"A visual confirmation step will follow. "
            f"Fall detection is supportive and not a substitute for a medical alert system."
        )

    return (
        f"Signal of type '{kind}' fired during the window "
        f"{window_start or 'unknown start'} to {window_end or 'unknown end'}. "
        f"Review the evidence timeline for details."
    )
