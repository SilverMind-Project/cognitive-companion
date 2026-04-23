"""Shared Pydantic type aliases used across all API schemas.

Why UTCDatetime?
----------------
SQLite has no native datetime type, and legacy values or non-ORM code paths may
still surface naive ``datetime`` objects. Pydantic serialises those the same
way: no ``Z``, no ``+00:00``.

JavaScript's ``new Date()`` treats timezone-naive ISO strings as *local* browser
time (ECMAScript 2015+), not UTC.  When the browser timezone differs from UTC
the resulting instant is wrong and the frontend displays the incorrect time.

``UTCDatetime`` is an annotated ``datetime`` that always serialises with a
trailing ``Z`` in JSON, signalling unambiguous UTC to every consumer of the API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import PlainSerializer

from backend.core.time import normalize_utc_datetime


def _to_utc_iso(v: datetime | None) -> str | None:
    """Serialise *v* as a UTC ISO-8601 string with a trailing ``Z``."""
    if v is None:
        return None
    normalized = normalize_utc_datetime(v)
    if normalized is None:
        return None
    return normalized.isoformat().replace("+00:00", "Z")


#: Drop-in replacement for ``datetime`` in Pydantic output schemas.
#: Validates identically to ``datetime``; serialises to JSON with "Z" suffix.
UTCDatetime = Annotated[datetime, PlainSerializer(_to_utc_iso, when_used="json")]

#: Nullable variant of UTCDatetime.
OptionalUTCDatetime = Annotated[datetime | None, PlainSerializer(_to_utc_iso, when_used="json")]
