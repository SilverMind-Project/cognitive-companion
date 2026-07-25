"""SignalsService: async read API for CTS dementia signals.

Wraps :class:`~backend.services.cts.signal_store.SignalStore` so pipeline
steps never touch ``db_factory`` or ``SignalStore`` directly.

All methods are async and accept a ``db_factory`` callable that returns
a SQLAlchemy ``Session``.  Tests inject a factory backed by the shared
PostgreSQL fixture.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from backend.services.cts.signal_config import CC_LOCAL_SIGNAL_KINDS
from backend.services.cts.signal_store import SignalStore, derive_signal_id


class SignalsService:
    """Async wrapper around :class:`SignalStore` with severity mapping
    and deduplication.

    Parameters
    ----------
    db_factory:
        Callable that returns a new SQLAlchemy ``Session``.  In production
        this is ``backend.core.database.get_session``; in tests it wraps
        the PostgreSQL fixture.
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
            part, _ = await store.list_recent(
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

    async def emit(
        self,
        *,
        signal_kind: str,
        person_id: str,
        severity: str = "info",
        value: float = 1.0,
        context: dict[str, Any] | None = None,
        dedupe_minutes: int = 60,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Write a CC-local signal (see ``signal_config.CC_LOCAL_SIGNAL_KINDS``).

        This is the single write path for CC-local signals emitted from
        pipelines (the ``signal_emit`` step); it never accepts a wire
        (CTS-produced) kind, mirroring the CTS write-seam rule for
        semantic memory.

        Deduplicates against an unacknowledged signal of the same kind and
        person received within ``dedupe_minutes`` (``0`` disables dedup).
        The window comparison uses the injected ``now`` (defaults to
        ``datetime.now(UTC)``) rather than the store's own clock, so tests
        can advance a fake clock without sleeping.

        Every accepted emission is its own countable row: ``signal_id`` is
        derived from ``person_id``, ``signal_kind``, and this call's
        timestamp (via the shared ``derive_signal_id`` helper), so it never
        collides with a prior emission the way a fixed per-kind id would.
        ``evidence_grade="experimental"`` is set unconditionally, because
        ``SignalStore.acknowledge()`` only persists caregiver feedback for
        that grade; without it, every accurate/inaccurate label a caregiver
        gives would be silently dropped and the precision measurement this
        signal exists for would never have any labeled data.

        Returns ``{"emitted": bool, "reason": str | None, "signal_row_id": int | None}``.
        ``reason`` is ``"invalid_kind"`` or ``"deduped"`` when ``emitted`` is
        ``False``.
        """
        if signal_kind not in CC_LOCAL_SIGNAL_KINDS:
            return {"emitted": False, "reason": "invalid_kind", "signal_row_id": None}

        now = now or datetime.now(UTC)
        store = SignalStore(db_factory=self._db_factory)

        if dedupe_minutes > 0:
            # window_hours only bounds the SQL-side lookback (against the
            # store's own, uninjectable received_at clock); a just-written
            # row's received_at is always "now" in wall-clock terms, so any
            # window_hours >= 1 reliably includes it regardless of the fake
            # `now` this method was given. The actual dedupe comparison below
            # uses window_end, which we set from the injected `now` on write,
            # so it is what tests can control without sleeping.
            window_hours = max(1, (dedupe_minutes + 59) // 60)
            recent = await store.get_unacknowledged(person_id=person_id, window_hours=window_hours)
            cutoff = now - timedelta(minutes=dedupe_minutes)
            for sig in recent:
                if sig.get("signal_type") != signal_kind:
                    continue
                window_end_raw = sig.get("window_end")
                if window_end_raw is None:
                    continue
                window_end = datetime.fromisoformat(window_end_raw)
                if window_end.tzinfo is None:
                    window_end = window_end.replace(tzinfo=UTC)
                if window_end >= cutoff:
                    return {"emitted": False, "reason": "deduped", "signal_row_id": None}

        now_iso = now.isoformat()
        signal_id = derive_signal_id(person_id, signal_kind, now_iso, now_iso)
        row_id, _action = await store.upsert(
            {
                "signal_id": signal_id,
                "person_id": person_id,
                "signal_type": signal_kind,
                "severity": severity,
                "window_start": now_iso,
                "window_end": now_iso,
                "value": value,
                "context_json": context,
                "evidence_grade": "experimental",
            }
        )
        return {"emitted": True, "reason": None, "signal_row_id": row_id}
