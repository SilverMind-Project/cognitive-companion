"""Prometheus metrics for CTS subscribers.

Counters track received, persisted, decode errors, and dropped messages
so that silent signal loss becomes visible to operators.
"""

from __future__ import annotations

from prometheus_client import Counter

SIGNAL_KIND_LABEL = "signal_kind"
EVENT_TYPE_LABEL = "event_type"

# -- DementiaSignal counters --------------------------------------------------

cts_signals_received = Counter(
    "cts_signals_received_total",
    "Total tracking.signals messages received from Redis Stream.",
    [SIGNAL_KIND_LABEL],
)

cts_signals_persisted = Counter(
    "cts_signals_persisted_total",
    "Total tracking.signals messages successfully persisted.",
    [SIGNAL_KIND_LABEL],
)

cts_signals_decode_errors = Counter(
    "cts_signals_decode_errors_total",
    "Total tracking.signals messages that failed proto decode.",
)

cts_signals_dropped = Counter(
    "cts_signals_dropped_total",
    "Total tracking.signals messages dropped (decode failure, missing fields, or storage error).",
    [SIGNAL_KIND_LABEL],
)

# -- TrackingEvent counters ---------------------------------------------------

cts_events_received = Counter(
    "cts_events_received_total",
    "Total tracking.events messages received from Redis Stream.",
    [EVENT_TYPE_LABEL],
)

cts_events_persisted = Counter(
    "cts_events_persisted_total",
    "Total tracking.events messages successfully persisted.",
    [EVENT_TYPE_LABEL],
)

cts_events_decode_errors = Counter(
    "cts_events_decode_errors_total",
    "Total tracking.events messages that failed proto decode.",
)

cts_events_dropped = Counter(
    "cts_events_dropped_total",
    "Total tracking.events messages dropped.",
    [EVENT_TYPE_LABEL],
)

cts_events_stale_dropped = Counter(
    "cts_events_stale_dropped_total",
    "Total tracking.events messages dropped because capture_time_unix_ns"
    " was older than the max-event-age threshold.",
)

# -- IdentityRevision counters ------------------------------------------------

cts_revisions_received = Counter(
    "cts_revisions_received_total",
    "Total tracking.revisions messages received from Redis Stream.",
)

cts_revisions_persisted = Counter(
    "cts_revisions_persisted_total",
    "Total tracking.revisions messages successfully persisted.",
)

cts_revisions_decode_errors = Counter(
    "cts_revisions_decode_errors_total",
    "Total tracking.revisions messages that failed proto decode.",
)

cts_revisions_dropped = Counter(
    "cts_revisions_dropped_total",
    "Total tracking.revisions messages dropped.",
)

# -- FrameResponse (tracking.responses) counters ------------------------------

OUTCOME_LABEL = "outcome"

cts_tracking_responses_received = Counter(
    "cts_tracking_responses_received_total",
    "Total tracking.responses messages received from Redis Stream.",
    [OUTCOME_LABEL],
)

cts_tracking_responses_decode_errors = Counter(
    "cts_tracking_responses_decode_errors_total",
    "Total tracking.responses messages that failed proto decode.",
)
