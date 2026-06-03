"""SignalsFeedService: one caregiver-facing feed across all sources.

Unions:
* CTS dementia signals (``cts_signals`` via :class:`SignalStore`) -- rich
  severity, acknowledgeable, deletable.
* Pipeline rules that fired a notification (``event_logs`` whose persisted
  pipeline snapshot contains a notification step with
  ``notification_dispatched=True``) -- severity carried through from the
  notification step's ``alert_level``; read-only in the feed.

Both are normalised to :class:`SignalEnvelope`. This is the single service
function behind ``GET /api/v1/signals/feed`` and the MCP ``get_signals_feed``
tool (D6 parity).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.event import EventLog
from backend.models.person import HouseholdMember
from backend.schemas.signals_feed import SEVERITY_RANK, SignalEnvelope
from backend.services.cts.signal_store import SignalStore

logger = get_logger(__name__)

# How many recent completed event-logs to scan for notification outcomes.
# The feed itself is small (dashboard widget); this bounds the JSON scan.
_EVENTLOG_SCAN_LIMIT = 200


class SignalsFeedService:
    """Cross-source caregiver alert feed keyed on a unified envelope."""

    def __init__(self, db_factory: Callable[[], Session]) -> None:
        self._db_factory = db_factory
        self._store = SignalStore(db_factory=db_factory)

    async def list_feed(
        self,
        *,
        source: str | None = None,
        severity_min: str = "info",
        person_id: str | None = None,
        room_name: str | None = None,
        window_hours: int = 24,
        limit: int = 50,
    ) -> list[SignalEnvelope]:
        """Return the merged feed, most-recent first."""
        envelopes: list[SignalEnvelope] = []
        if source in (None, "cts"):
            envelopes.extend(
                await self._cts_signals(
                    person_id=person_id, window_hours=window_hours, limit=limit
                )
            )
        if source in (None, "pipeline_rule"):
            envelopes.extend(self._pipeline_rule_alerts(window_hours=window_hours))

        min_rank = SEVERITY_RANK.get(severity_min, 0)
        filtered = [e for e in envelopes if SEVERITY_RANK.get(e.severity, 0) >= min_rank]
        if room_name:
            filtered = [e for e in filtered if e.room_name == room_name]
        if person_id:
            filtered = [e for e in filtered if e.person_id == person_id]

        filtered.sort(key=lambda e: e.created_at or datetime.min.replace(tzinfo=UTC), reverse=True)
        return filtered[:limit]

    # -- CTS dementia signals ------------------------------------------------

    async def _cts_signals(
        self, *, person_id: str | None, window_hours: int, limit: int
    ) -> list[SignalEnvelope]:
        rows, _ = await self._store.list_recent(
            person_id=person_id, window_hours=window_hours, limit=limit
        )
        names = self._display_names({r.get("person_id") for r in rows if r.get("person_id")})
        out: list[SignalEnvelope] = []
        for r in rows:
            ctx = r.get("context_json") or {}
            pid = r.get("person_id")
            out.append(
                SignalEnvelope(
                    id=f"cts:{r.get('id')}",
                    source="cts",
                    kind=str(r.get("signal_type", "")),
                    severity=str(r.get("severity", "info")),
                    room_id=ctx.get("room_id") if isinstance(ctx, dict) else None,
                    room_name=ctx.get("room_name") if isinstance(ctx, dict) else None,
                    person_id=pid,
                    display_name=names.get(pid),
                    created_at=_parse_iso(r.get("received_at") or r.get("window_end")),
                    resolved=r.get("acknowledged_at") is not None,
                    detail=str(r.get("signal_type", "")).replace("_", " ").capitalize(),
                    can_acknowledge=True,
                    can_delete=True,
                )
            )
        return out

    # -- Pipeline rule notifications -----------------------------------------

    def _pipeline_rule_alerts(self, *, window_hours: int) -> list[SignalEnvelope]:
        since = datetime.now(UTC) - timedelta(hours=window_hours)
        db = self._db_factory()
        try:
            stmt = (
                select(EventLog)
                .where(EventLog.status == "completed", EventLog.timestamp >= since)
                .order_by(EventLog.timestamp.desc())
                .limit(_EVENTLOG_SCAN_LIMIT)
            )
            rows = db.execute(stmt).scalars().all()
            out: list[SignalEnvelope] = []
            for log in rows:
                notif = _extract_notification(log.pipeline_data_json)
                if notif is None:
                    continue
                out.append(
                    SignalEnvelope(
                        id=f"rule:{log.id}",
                        source="pipeline_rule",
                        kind=log.rule_name or "rule",
                        severity=notif.get("severity", "info"),
                        room_id=None,
                        room_name=notif.get("room_name") or log.room_name,
                        person_id=None,
                        display_name=None,
                        created_at=log.timestamp,
                        resolved=False,
                        detail=notif.get("message", ""),
                        can_acknowledge=False,
                        can_delete=False,
                    )
                )
            return out
        finally:
            db.close()

    # -- helpers -------------------------------------------------------------

    def _display_names(self, ids: set[str | None]) -> dict[str | None, str]:
        clean = {i for i in ids if i}
        if not clean:
            return {}
        db = self._db_factory()
        try:
            members = (
                db.query(HouseholdMember).filter(HouseholdMember.id.in_(clean)).all()
            )
            return {m.id: m.name for m in members}
        finally:
            db.close()


def _extract_notification(pipeline_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return notification outcome from a persisted pipeline snapshot, if any.

    Step outputs live under ``steps.<label>.outputs``; we match on
    ``step_type == "notification"`` (label-independent) and require that a
    notification was actually dispatched.
    """
    if not isinstance(pipeline_data, dict):
        return None
    steps = pipeline_data.get("steps")
    if not isinstance(steps, dict):
        return None
    for entry in steps.values():
        if not isinstance(entry, dict) or entry.get("step_type") != "notification":
            continue
        outputs = entry.get("outputs")
        if isinstance(outputs, dict) and outputs.get("notification_dispatched"):
            return {
                "severity": str(outputs.get("notification_severity", "info")),
                "message": str(outputs.get("notification_message", "")),
                "room_name": outputs.get("notification_room_name"),
            }
    return None


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
