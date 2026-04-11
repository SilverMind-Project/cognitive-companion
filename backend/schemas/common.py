"""Shared Pydantic type aliases used across all API schemas.

Why UTCDatetime?
----------------
SQLite has no native datetime type; SQLAlchemy stores datetimes as text strings
without a timezone suffix (e.g. "2026-04-11T11:57:30").  Pydantic serialises
naive ``datetime`` objects the same way — no ``Z``, no ``+00:00``.

JavaScript's ``new Date()`` treats timezone-naive ISO strings as *local* browser
time (ECMAScript 2015+), not UTC.  When the browser timezone differs from UTC
the resulting instant is wrong and the frontend displays the incorrect time.

``UTCDatetime`` is an annotated ``datetime`` that always serialises with a
trailing ``Z`` in JSON, signalling unambiguous UTC to every consumer of the API.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import PlainSerializer


def _to_utc_iso(v: datetime | None) -> str | None:
    """Serialise *v* as a UTC ISO-8601 string with a trailing ``Z``."""
    if v is None:
        return None
    if v.tzinfo is None:
        # Naive datetimes from SQLite are always UTC by convention.
        v = v.replace(tzinfo=UTC)
    return v.isoformat().replace("+00:00", "Z")


#: Drop-in replacement for ``datetime`` in Pydantic output schemas.
#: Validates identically to ``datetime``; serialises to JSON with "Z" suffix.
UTCDatetime = Annotated[datetime, PlainSerializer(_to_utc_iso, when_used="json")]

#: Nullable variant of UTCDatetime.
OptionalUTCDatetime = Annotated[datetime | None, PlainSerializer(_to_utc_iso, when_used="json")]
