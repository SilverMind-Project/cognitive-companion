"""Prometheus metrics for CTS subscribers.

Counters track received, persisted, decode errors, and dropped messages
so that silent signal loss becomes visible to operators.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

SIGNAL_KIND_LABEL = "signal_kind"
EVENT_TYPE_LABEL = "event_type"

# -- M09 ReID review-queue metrics --------------------------------------------

REVIEW_ACTION_LABEL = "action"  # approve | relabel | reject | reject_batch | compensate

cts_reid_review_actions_total = Counter(
    "cts_reid_review_actions_total",
    "Total ReID review-queue operator actions by type.",
    [REVIEW_ACTION_LABEL],
)

cts_reid_review_relabels_total = Counter(
    "cts_reid_review_relabels_total",
    "Total ReID review-queue relabel actions (a relabel is also counted as an action).",
)

cts_reid_review_failures_total = Counter(
    "cts_reid_review_failures_total",
    "Total ReID review-queue actions that failed (stale, ineligible, or upstream error).",
    [REVIEW_ACTION_LABEL],
)

cts_reid_review_action_latency_seconds = Histogram(
    "cts_reid_review_action_latency_seconds",
    "Wall-clock latency of a ReID review-queue mutation round-trip to the orchestrator.",
    [REVIEW_ACTION_LABEL],
)

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

# -- Identity-continuity M05 backfill projector counters ----------------------

BACKFILL_OUTCOME_LABEL = (
    "outcome"  # applied | skipped_duplicate | dropped_invalid | overlap_skipped
)

cc_cts_backfill_projections_total = Counter(
    "cc_cts_backfill_projections_total",
    "Total inferred_backfill revisions processed by the CC backfill projector.",
    [BACKFILL_OUTCOME_LABEL],
)

cc_cts_backfill_rows_inserted_total = Counter(
    "cc_cts_backfill_rows_inserted_total",
    "Total presence_segments rows inserted by the CC backfill projector.",
)


# -- Filter degradation counters -------------------------------------------

FILTER_LABEL = "filter"

cts_filter_degraded_total = Counter(
    "cts_filter_degraded_total",
    "Total CTS filter evaluations that failed closed because PersonLocationService was unavailable.",
    [FILTER_LABEL],
)
