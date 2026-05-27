"""SignalStore: persistence and read API for CTS dementia signals.

This module is the sole database-facing layer for dementia signals in
Cognitive Companion.  The DementiaSignalSubscriber delegates inserts to
SignalStore; the cts_signals router delegates reads to it.

All methods are async and accept a ``db_factory`` callable that returns
a SQLAlchemy ``Session``.  Tests inject a factory backed by the in-memory
SQLite fixture.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from backend.models.cts_signal import DementiaSignal
from backend.services.cts._time import parse_ts


class SignalStore:
    """Async wrapper around the ``DementiaSignal`` ORM model.

    Parameters
    ----------
    db_factory:
        Callable that returns a new SQLAlchemy ``Session``.  In production
        this is ``backend.core.database.get_session``; in tests it wraps
        the in-memory fixture.
    """

    def __init__(self, db_factory: Callable[[], Session]) -> None:
        self._db_factory = db_factory

    # -- Write path ----------------------------------------------------------

    async def insert(self, signal_data: dict[str, Any]) -> int:
        """Insert a single dementia signal (backward-compatible wrapper).

        Prefer ``upsert()`` for new code; it returns the action taken
        (``new`` / ``escalation`` / ``update``) so callers can gate
        notifications on severity transitions.
        """
        row_id, _ = await self.upsert(signal_data)
        return row_id

    async def upsert(self, signal_data: dict[str, Any]) -> tuple[int, str]:
        """Insert or update a dementia signal with severity-transition semantics.

        Returns ``(row_id, action)`` where *action* is one of:

        - ``"new"`` — a new signal_id was inserted (actionable).
        - ``"escalation"`` — same signal_id, higher severity (actionable).
        - ``"update"`` — same signal_id, equal or lower severity (no-op for
          notification purposes; consumers should not re-alert).
        """
        db = self._db_factory()
        try:
            signal_id = signal_data.get("signal_id")
            new_severity = signal_data["severity"]
            sev_order = {"info": 0, "warning": 1, "emergency": 2}
            new_sev_rank = sev_order.get(new_severity, 0)

            if signal_id:
                existing = (
                    db.query(DementiaSignal).filter(DementiaSignal.signal_id == signal_id).first()
                )
            else:
                existing = None

            if existing is None:
                # New signal — insert.
                row = DementiaSignal(
                    signal_id=signal_id,
                    person_id=signal_data["person_id"],
                    signal_type=signal_data["signal_type"],
                    severity=new_severity,
                    window_start=parse_ts(signal_data["window_start"]),
                    window_end=parse_ts(signal_data["window_end"]),
                    value=float(signal_data["value"]),
                    baseline=float(signal_data["baseline"])
                    if signal_data.get("baseline") is not None
                    else None,
                    z_score=float(signal_data["z_score"])
                    if signal_data.get("z_score") is not None
                    else None,
                    context_json=signal_data.get("context_json"),
                    algorithm_version=signal_data.get("algorithm_version"),
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                return row.id, "new"

            # Existing signal — check severity transition.
            old_sev_rank = sev_order.get(existing.severity, 0)
            existing.severity = new_severity
            existing.value = float(signal_data["value"])
            existing.baseline = (
                float(signal_data["baseline"]) if signal_data.get("baseline") is not None else None
            )
            existing.z_score = (
                float(signal_data["z_score"]) if signal_data.get("z_score") is not None else None
            )
            existing.context_json = signal_data.get("context_json")
            existing.algorithm_version = signal_data.get("algorithm_version")
            existing.window_end = parse_ts(signal_data["window_end"])
            db.commit()
            db.refresh(existing)

            if new_sev_rank > old_sev_rank:
                return existing.id, "escalation"
            return existing.id, "update"
        finally:
            db.close()

    async def delete(self, signal_id: int) -> bool:
        """Hard-delete a single dementia signal by row ID.

        Returns ``True`` if a row was deleted, ``False`` if not found.
        Note: the orchestrator may re-insert the same logical signal if it
        republishes via the Redis stream; callers accept this risk.
        """
        db = self._db_factory()
        try:
            row = db.query(DementiaSignal).filter(DementiaSignal.id == signal_id).first()
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True
        finally:
            db.close()

    async def batch_delete(self, signal_ids: list[int]) -> int:
        """Hard-delete multiple dementia signals by row IDs.

        Returns the count of rows actually deleted.
        """
        if not signal_ids:
            return 0
        db = self._db_factory()
        try:
            rows = db.query(DementiaSignal).filter(DementiaSignal.id.in_(signal_ids)).all()
            for row in rows:
                db.delete(row)
            db.commit()
            return len(rows)
        finally:
            db.close()

    async def acknowledge(self, signal_id: int) -> bool:
        """Mark a signal as acknowledged by a caregiver.

        Returns ``True`` if a row was updated, ``False`` if not found.
        """
        db = self._db_factory()
        try:
            row = db.query(DementiaSignal).filter(DementiaSignal.id == signal_id).first()
            if row is None:
                return False
            row.acknowledged_at = datetime.now(UTC)
            db.commit()
            return True
        finally:
            db.close()

    # -- Read paths ----------------------------------------------------------

    async def list_recent(
        self,
        *,
        person_id: str | None = None,
        signal_type: str | None = None,
        severity: str | None = None,
        window_hours: int = 24,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return recent dementia signals as serialisable dicts plus total count.

        Filters are applied with AND logic; ``None`` means "no filter".
        Returns ``(rows, total)`` where *total* is the unsliced match count.
        """
        db = self._db_factory()
        try:
            now = datetime.now(UTC)
            since = now - timedelta(hours=window_hours)

            base = select(DementiaSignal).where(DementiaSignal.received_at >= since)
            if person_id:
                base = base.where(DementiaSignal.person_id == person_id)
            if signal_type:
                base = base.where(DementiaSignal.signal_type == signal_type)
            if severity:
                base = base.where(DementiaSignal.severity == severity)

            total: int = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()

            rows = (
                db.execute(
                    base.order_by(desc(DementiaSignal.received_at)).limit(limit).offset(offset)
                )
                .scalars()
                .all()
            )

            return [self._to_dict(r) for r in rows], total
        finally:
            db.close()

    async def get_unacknowledged(
        self,
        *,
        person_id: str | None = None,
        severity: str | None = None,
        window_hours: int = 24,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return unacknowledged signals (for alerting / dashboard)."""
        db = self._db_factory()
        try:
            now = datetime.now(UTC)
            since = now - timedelta(hours=window_hours)

            q = select(DementiaSignal).where(
                DementiaSignal.acknowledged_at.is_(None),
                DementiaSignal.received_at >= since,
            )
            if person_id:
                q = q.where(DementiaSignal.person_id == person_id)
            if severity:
                q = q.where(DementiaSignal.severity == severity)

            q = q.order_by(desc(DementiaSignal.received_at)).limit(limit)
            rows = db.execute(q).scalars().all()

            return [self._to_dict(r) for r in rows]
        finally:
            db.close()

    async def get_24h_summary(self, person_id: str | None = None) -> dict[str, Any]:
        """Return a 24-hour summary for the dashboard.

        Returns a dict keyed by signal_type with counts and max severity.
        """
        db = self._db_factory()
        try:
            now = datetime.now(UTC)
            since = now - timedelta(hours=24)

            base_q = select(
                DementiaSignal.signal_type,
                func.count(DementiaSignal.id).label("count"),
                func.max(
                    case(
                        (DementiaSignal.severity == "emergency", 3),
                        (DementiaSignal.severity == "warning", 2),
                        else_=1,
                    )
                ).label("max_severity_rank"),
            ).where(
                DementiaSignal.received_at >= since,
            )
            if person_id:
                base_q = base_q.where(DementiaSignal.person_id == person_id)

            base_q = base_q.group_by(DementiaSignal.signal_type)
            rows = db.execute(base_q).all()

            severity_labels = {3: "emergency", 2: "warning", 1: "info"}
            summary: dict[str, Any] = {}
            for row in rows:
                summary[row.signal_type] = {
                    "count": row.count,
                    "max_severity": severity_labels.get(row.max_severity_rank, "info"),
                }

            total = sum(s["count"] for s in summary.values())
            return {
                "window_hours": 24,
                "person_id": person_id,
                "total_signals": total,
                "by_type": summary,
            }
        finally:
            db.close()

    async def get_daily_trend(
        self,
        person_id: str,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """Return per-day signal counts for trend charts.

        Returns a list of dicts with ``date``, ``count``, and
        ``by_severity`` keys.
        """
        db = self._db_factory()
        try:
            now = datetime.now(UTC)
            since = now - timedelta(days=days)

            rows = db.execute(
                select(
                    func.date(DementiaSignal.received_at).label("day"),
                    DementiaSignal.severity,
                    func.count(DementiaSignal.id).label("count"),
                )
                .where(
                    DementiaSignal.person_id == person_id,
                    DementiaSignal.received_at >= since,
                )
                .group_by("day", DementiaSignal.severity)
                .order_by("day")
            ).all()

            # Pivot into per-day dicts.
            days_dict: dict[str, dict[str, Any]] = {}
            for i in range(days):
                day_str = (now - timedelta(days=days - 1 + i)).strftime("%Y-%m-%d")
                days_dict[day_str] = {"date": day_str, "count": 0, "by_severity": {}}

            for row in rows:
                day_str = row.day.isoformat() if hasattr(row.day, "isoformat") else str(row.day)
                if day_str not in days_dict:
                    days_dict[day_str] = {"date": day_str, "count": 0, "by_severity": {}}
                entry = days_dict[day_str]
                entry["count"] += row.count
                entry["by_severity"][row.severity] = row.count

            return list(days_dict.values())
        finally:
            db.close()

    async def aggregate_by_kind(
        self,
        *,
        person_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """SQL GROUP BY kind — never Python post-processing."""
        db = self._db_factory()
        try:
            q = select(
                DementiaSignal.signal_type,
                func.count(DementiaSignal.id).label("count"),
            ).group_by(DementiaSignal.signal_type).order_by(
                desc(func.count(DementiaSignal.id))
            )
            if person_id is not None:
                q = q.where(DementiaSignal.person_id == person_id)
            if since is not None:
                q = q.where(DementiaSignal.received_at >= since)
            if until is not None:
                q = q.where(DementiaSignal.received_at <= until)
            rows = db.execute(q).all()
            return [{"kind": r.signal_type, "count": r.count} for r in rows]
        finally:
            db.close()

    async def aggregate_by_room(
        self,
        *,
        person_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """SQL GROUP BY room_name from context_json."""
        db = self._db_factory()
        try:
            room_expr = func.json_extract(
                DementiaSignal.context_json, "$.room_name"
            ).label("room_name")
            q = (
                select(
                    room_expr,
                    func.count(DementiaSignal.id).label("count"),
                )
                .where(DementiaSignal.context_json.isnot(None))
                .group_by(room_expr)
                .order_by(desc(func.count(DementiaSignal.id)))
            )
            if person_id is not None:
                q = q.where(DementiaSignal.person_id == person_id)
            if since is not None:
                q = q.where(DementiaSignal.received_at >= since)
            if until is not None:
                q = q.where(DementiaSignal.received_at <= until)
            rows = db.execute(q).all()
            return [
                {"room_name": r.room_name, "count": r.count}
                for r in rows
                if r.room_name
            ]
        finally:
            db.close()

    # -- Helpers -------------------------------------------------------------

    @staticmethod
    def _to_dict(row: DementiaSignal) -> dict[str, Any]:
        return {
            "id": row.id,
            "signal_id": row.signal_id,
            "person_id": row.person_id,
            "signal_type": row.signal_type,
            "severity": row.severity,
            "window_start": row.window_start.isoformat() if row.window_start else None,
            "window_end": row.window_end.isoformat() if row.window_end else None,
            "value": row.value,
            "baseline": row.baseline,
            "z_score": row.z_score,
            "context_json": row.context_json,
            "algorithm_version": row.algorithm_version,
            "acknowledged_at": row.acknowledged_at.isoformat() if row.acknowledged_at else None,
            "received_at": row.received_at.isoformat() if row.received_at else None,
        }
