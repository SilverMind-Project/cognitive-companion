"""SignalsService: async read API for CTS dementia signals.

Wraps :class:`~backend.services.cts.signal_store.SignalStore` so pipeline
steps never touch ``db_factory`` or ``SignalStore`` directly.

All methods are async and accept a ``db_factory`` callable that returns
a SQLAlchemy ``Session``.  Tests inject a factory backed by the in-memory
SQLite fixture.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from backend.services.cts.signal_store import SignalStore


class SignalsService:
    """Async wrapper around :class:`SignalStore` with severity mapping
    and deduplication.

    Parameters
    ----------
    db_factory:
        Callable that returns a new SQLAlchemy ``Session``.  In production
        this is ``backend.core.database.get_session``; in tests it wraps
        the in-memory fixture.
    """

    def __init__(self, db_factory) -> None:
        self._db_factory = db_factory

    async def list_recent(
        self,
        *,
        person_id: str | None = None,
        signal_kind: str | None = None,
        severity_min: str = "info",
        window_minutes: int = 30,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Return recent dementia signals matching the filters.

        Severity is inclusive: ``severity_min="warning"`` returns signals
        with severity ``warning`` or ``emergency``.

        Parameters
        ----------
        person_id:
            Filter to this person. ``None`` matches all persons.
        signal_kind:
            Filter to this signal type (e.g. ``"bathroom_dwell_anomaly"``).
            ``None`` matches all types.
        severity_min:
            Minimum severity to include.  One of ``"info"``,
            ``"warning"``, ``"emergency"``.
        window_minutes:
            Lookback window in minutes.
        limit:
            Maximum signals to return per severity tier.

        Returns
        -------
        list[dict[str, Any]]
            Deduplicated signal dicts, ordered most-recent first.
        """
        order = ["info", "warning", "emergency"]
        try:
            idx = order.index(severity_min)
        except ValueError:
            idx = 0
        accept = order[idx:]

        store = SignalStore(db_factory=self._db_factory)
        results: list[dict[str, Any]] = []
        for sev in accept:
            part = await store.list_recent(
                person_id=person_id,
                signal_type=signal_kind,
                severity=sev,
                window_hours=max(1, (window_minutes + 59) // 60),
                limit=limit,
            )
            results.extend(part)

        # Hard filter to the minute-based window (SignalStore uses hours).
        cutoff = datetime.now(UTC) - timedelta(minutes=window_minutes)
        filtered: list[dict[str, Any]] = []
        for sig in results:
            raw = sig.get("received_at")
            if raw is None:
                filtered.append(sig)
                continue
            try:
                ts = datetime.fromisoformat(raw)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                if ts >= cutoff:
                    filtered.append(sig)
            except ValueError:
                continue

        # Deduplicate by id, preserve recent-first order.
        seen: set[int] = set()
        deduped: list[dict[str, Any]] = []
        for sig in filtered:
            sid = sig.get("id")
            if isinstance(sid, int) and sid in seen:
                continue
            if isinstance(sid, int):
                seen.add(sid)
            deduped.append(sig)
        return deduped
