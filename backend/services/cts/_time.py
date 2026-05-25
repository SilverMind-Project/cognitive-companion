"""Shared time-parsing utilities for CTS services.

Replaces verbatim-duplicated helpers across 7 files:
- ``_ns_to_iso`` (4 copies: tracking_event, identity_revision, dementia_signal, scene_sample subscribers)
- ``_parse_ts`` (3 copies with 3 different signatures: identity_rewriter, location_writer, signal_store)
- ``_ensure_aware`` (1 copy: source_authority)
"""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["ensure_aware", "ns_to_iso", "parse_ts"]


def ns_to_iso(ns: int) -> str:
    """Convert Unix-nanosecond timestamp to ISO-8601 UTC string."""
    if ns <= 0:
        return datetime.now(UTC).isoformat()
    return datetime.fromtimestamp(ns / 1e9, tz=UTC).isoformat()


def parse_ts(value: str | datetime | None) -> datetime:
    """Normalise an ISO-8601 string, datetime, or None into a UTC-aware datetime.

    None → current UTC time.
    Naive datetime → assumed UTC.
    Malformed ISO string → logged and returned as current UTC time.
    """
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        dt = datetime.fromisoformat(value)
    except ValueError, TypeError:
        return datetime.now(UTC)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def ensure_aware(dt: datetime) -> datetime:
    """Return *dt* as UTC-aware (no-op if already aware)."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
