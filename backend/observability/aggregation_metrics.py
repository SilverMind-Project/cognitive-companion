"""Prometheus metrics for camera aggregation rate limiting."""

from __future__ import annotations

from prometheus_client import Counter

aggregator_images_dropped = Counter(
    "cc_aggregator_images_dropped_total",
    "Images dropped by the per-camera rate limiter",
    labelnames=("camera_id", "origin"),
)
