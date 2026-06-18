"""Observability metrics for the unified person location service."""

from __future__ import annotations

from dataclasses import dataclass

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram


@dataclass
class LocationMetrics:
    observations_total: Counter
    segments_open: Gauge
    segments_opened_total: Counter
    segments_closed_total: Counter
    inferred_dwell_alerts_total: Counter
    identity_revisions_applied_total: Counter
    subscriber_lag_s: Histogram
    cts_orchestrator_unavailable_total: Counter  # U2: orchestrator unreachable counter
    mcp_tool_dependency_unavailable_total: Counter  # U2: MCP tool dependency unavailable
    guided_sessions_total: Counter
    guided_steps_total: Counter
    guided_escalations_total: Counter
    guided_vision_calls_total: Counter
    guided_vision_uncertain_total: Counter
    guided_takeovers_total: Counter


def build_location_metrics(registry: CollectorRegistry = REGISTRY) -> LocationMetrics:
    def _counter(name: str, doc: str, labels: list[str] | None = None) -> Counter:
        return Counter(name, doc, labelnames=labels or [], registry=registry)

    def _gauge(name: str, doc: str, labels: list[str] | None = None) -> Gauge:
        return Gauge(name, doc, labelnames=labels or [], registry=registry)

    def _hist(
        name: str, doc: str, buckets: tuple[float, ...], labels: list[str] | None = None
    ) -> Histogram:
        return Histogram(name, doc, labelnames=labels or [], buckets=buckets, registry=registry)

    return LocationMetrics(
        observations_total=_counter(
            "cc_location_observations_total",
            "Location observations ingested",
            ["source"],
        ),
        segments_open=_gauge(
            "cc_location_segments_open",
            "Currently-open presence segments",
        ),
        segments_opened_total=_counter(
            "cc_location_segments_opened_total",
            "Segments opened since process start",
            ["entry_source"],
        ),
        segments_closed_total=_counter(
            "cc_location_segments_closed_total",
            "Segments closed since process start",
            ["exit_source"],
        ),
        inferred_dwell_alerts_total=_counter(
            "cc_inferred_dwell_alerts_total",
            "inferred_dwell_exceeded signals fired",
            ["room_id"],
        ),
        identity_revisions_applied_total=_counter(
            "cc_identity_revisions_applied_total",
            "Revisions applied to existing segments",
        ),
        subscriber_lag_s=_hist(
            "cc_location_subscriber_lag_s",
            "Subscriber processing latency from observed_at to write",
            (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
            ["stream"],
        ),
        cts_orchestrator_unavailable_total=_counter(
            "cc_cts_orchestrator_unavailable_total",
            "Times the CTS orchestrator was unreachable on a dashboard request",
            ["endpoint"],
        ),
        mcp_tool_dependency_unavailable_total=_counter(
            "cc_mcp_tool_dependency_unavailable_total",
            "Times an MCP tool found its upstream dependency unavailable",
            ["tool"],
        ),
        guided_sessions_total=_counter(
            "cc_guided_sessions_total",
            "Guided sessions finalized by outcome",
            ["outcome"],
        ),
        guided_steps_total=_counter(
            "cc_guided_steps_total",
            "Guided task steps by result",
            ["result"],
        ),
        guided_escalations_total=_counter(
            "cc_guided_escalations_total",
            "Guided task escalations by kind",
            ["kind"],
        ),
        guided_vision_calls_total=_counter(
            "cc_guided_vision_calls_total",
            "Guided task vision confirmation calls",
        ),
        guided_vision_uncertain_total=_counter(
            "cc_guided_vision_uncertain_total",
            "Guided task vision confirmation calls with uncertain result",
        ),
        guided_takeovers_total=_counter(
            "cc_guided_takeovers_total",
            "Guided task caregiver takeovers",
        ),
    )


# Module-level singleton for import by subscribers.
location_metrics = build_location_metrics()
