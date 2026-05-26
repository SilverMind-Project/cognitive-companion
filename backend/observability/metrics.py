"""M4 observability metrics for the unified person location service."""

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


def build_location_metrics(registry: CollectorRegistry = REGISTRY) -> LocationMetrics:
    def _counter(name: str, doc: str, labels: list[str] | None = None) -> Counter:
        return Counter(name, doc, labelnames=labels or [], registry=registry)

    def _gauge(name: str, doc: str, labels: list[str] | None = None) -> Gauge:
        return Gauge(name, doc, labelnames=labels or [], registry=registry)

    def _hist(name: str, doc: str, buckets: tuple[float, ...], labels: list[str] | None = None) -> Histogram:
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
    )


# Module-level singleton for import by subscribers.
location_metrics = build_location_metrics()
