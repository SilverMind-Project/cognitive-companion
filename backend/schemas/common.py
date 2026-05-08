"""Shared Pydantic type aliases used across all API schemas.

PostgreSQL UTC datetime contract
---------------------------------
All timestamp columns in the database use ``TIMESTAMPTZ``, which PostgreSQL
stores as UTC internally.  The ORM ``UTCDateTime`` type ensures that every
``datetime`` object read from the database is UTC-aware.

``UTCDatetime`` is an annotated ``AwareDatetime`` that always serialises with a
trailing ``Z`` in JSON (e.g. ``"2026-05-05T13:00:00Z"``), unambiguously
signalling UTC to every consumer of the API.

JavaScript's ``new Date()`` and ``Intl.DateTimeFormat`` handle ``Z``-suffixed
strings correctly regardless of browser timezone, so the frontend can safely
convert to the configured application timezone using ``Intl.DateTimeFormat``
with the ``timeZone`` option.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, PlainSerializer

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
#: Validates identically to ``AwareDatetime``; serialises to JSON with "Z" suffix.
UTCDatetime = Annotated[AwareDatetime, PlainSerializer(_to_utc_iso, when_used="json")]

#: Nullable variant of UTCDatetime.
OptionalUTCDatetime = Annotated[AwareDatetime | None, PlainSerializer(_to_utc_iso, when_used="json")]


# ── Shared base classes ──────────────────────────────────────────────────


class OutSchema(BaseModel):
    """Base for API output schemas: enables ORM-mode validation."""

    model_config = ConfigDict(from_attributes=True)


class CreateSchema(BaseModel):
    """Base for API create schemas: forbids extra fields."""

    model_config = ConfigDict(extra="forbid")


class UpdateSchema(BaseModel):
    """Base for API update schemas: all fields optional, extra fields forbidden."""

    model_config = ConfigDict(extra="forbid")
