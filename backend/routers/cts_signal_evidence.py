"""N7: Signal evidence, explorer, and weekly report endpoints.

Provides the practitioner-facing surface for reviewing dementia signal
evidence and generating weekly trend reports.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.core.auth import AuthContext, require_permission
from backend.core.logging import get_logger
from backend.routers.cts_deps import cts_enabled
from backend.services.cts.signal_narratives import narrative_for
from backend.services.cts.signal_store import SignalStore

logger = get_logger(__name__)

router = APIRouter(prefix="/cts", tags=["cts-signal-evidence"])


def _get_store(request: Request) -> SignalStore:
    from backend.core.database import get_session

    return SignalStore(db_factory=get_session)


# ---------------------------------------------------------------------------
# GET /cts/signals/{signal_id}/evidence
# ---------------------------------------------------------------------------


@router.get("/signals/{signal_id}/evidence")
async def signal_evidence(
    signal_id: int,
    request: Request,
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    store: SignalStore = Depends(_get_store),
) -> dict[str, Any]:
    """Return the full evidence backing a fired dementia signal."""
    cts_enabled()

    # Get the signal
    signals, _ = await store.list_recent(limit=200, offset=0, window_hours=720)
    signal = next((s for s in signals if s.get("id") == signal_id), None)
    if signal is None:
        raise HTTPException(status_code=404, detail={"code": "signal.not_found"})

    kind = signal.get("signal_type", "")
    window_start = signal.get("window_start")
    window_end = signal.get("window_end")
    person_id = signal.get("person_id", "")

    # Get presence segments in the window from PersonLocationService
    segments: list[dict] = []
    transitions: list[dict] = []
    try:
        pls = getattr(request.app.state, "person_location_service", None)
        if pls is not None and window_start and window_end:
            ws = _parse_iso(window_start) if isinstance(window_start, str) else window_start
            we = _parse_iso(window_end) if isinstance(window_end, str) else window_end
            segs = await pls.presence_history(str(person_id), ws, we)
            prev_room = None
            for seg in segs:
                segments.append(
                    {
                        "segment_id": str(seg.id),
                        "room_id": seg.room_id,
                        "room_name": str(seg.metadata.get("room_name", "")),
                        "entered_at": seg.entered_at.isoformat() if seg.entered_at else None,
                        "exited_at": seg.exited_at.isoformat() if seg.exited_at else None,
                        "dwell_seconds": ((seg.exited_at or we) - seg.entered_at).total_seconds(),
                        "entry_source": seg.entry_source,
                        "is_inferred": seg.is_inferred,
                    }
                )
                if prev_room is not None and seg.room_id != prev_room:
                    transitions.append(
                        {
                            "from_room_id": prev_room,
                            "to_room_id": seg.room_id,
                            "transitioned_at": seg.entered_at.isoformat() if seg.entered_at else None,
                        }
                    )
                prev_room = seg.room_id
    except Exception:
        logger.exception("signal_evidence_segments_failed")

    # Build narrative
    dwell_secs = signal.get("dwell_seconds", 0.0) or 0.0
    narrative = narrative_for(
        kind,
        room_name=signal.get("room_name", ""),
        threshold_min=signal.get("threshold_minutes", 0) or 0,
        actual_min=float(signal.get("value", 0.0) or 0.0),
        entered_at=str(signal.get("window_start", "")),
        dwell_seconds=dwell_secs,
        window_start=str(window_start or ""),
        window_end=str(window_end or ""),
        transition_count=len(transitions),
    )

    return {
        "signal": signal,
        "window": {"start": window_start, "end": window_end},
        "segments": segments,
        "transitions": transitions,
        "ph_lifecycle": {"ph_id": "", "started_at": None, "state": "active"},
        "keyframes": [],
        "narrative": narrative,
    }


# ---------------------------------------------------------------------------
# GET /cts/signals/explorer
# ---------------------------------------------------------------------------


@router.get("/signals/explorer")
async def signal_explorer(
    request: Request,
    kind: list[str] | None = Query(default=None, alias="kind[]"),
    severity: list[str] | None = Query(default=None, alias="severity[]"),
    person_id: list[str] | None = Query(default=None, alias="person_id[]"),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    store: SignalStore = Depends(_get_store),
) -> dict[str, Any]:
    """Rich signal explorer with multi-value filters and aggregates."""
    cts_enabled()

    window_hours = 720  # 30 days
    signals, _ = await store.list_recent(
        person_id=person_id[0] if person_id else None,
        signal_type=kind[0] if kind else None,
        severity=severity[0] if severity else None,
        window_hours=window_hours,
        limit=limit,
        offset=offset,
    )

    # Filter client-side for multi-value
    if kind and len(kind) > 1:
        signals = [s for s in signals if s.get("signal_type") in kind]
    if severity and len(severity) > 1:
        signals = [s for s in signals if s.get("severity") in severity]
    if person_id and len(person_id) > 1:
        signals = [s for s in signals if s.get("person_id") in person_id]

    # Aggregates
    by_kind: dict[str, int] = {}
    by_room: dict[str, int] = {}
    for s in signals:
        k = s.get("signal_type", "unknown")
        by_kind[k] = by_kind.get(k, 0) + 1
        room = s.get("room_name", "unknown")
        if room:
            by_room[room] = by_room.get(room, 0) + 1

    return {
        "rows": signals,
        "count": len(signals),
        "aggregates": {
            "by_kind": by_kind,
            "by_room": by_room,
        },
    }


# ---------------------------------------------------------------------------
# POST /cts/reports/weekly
# ---------------------------------------------------------------------------


class WeeklyReportRequest(BaseModel):
    person_id: str = Field(..., min_length=1)
    week_start: str = Field(..., description="ISO-8601 date (Monday)")


@router.post("/reports/weekly")
async def weekly_report(
    body: WeeklyReportRequest,
    request: Request,
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    store: SignalStore = Depends(_get_store),
) -> dict[str, Any]:
    """Generate a weekly trend report for a person."""
    cts_enabled()

    ws = _parse_iso(body.week_start)
    we = ws + timedelta(days=7)

    signals, _ = await store.list_recent(
        person_id=body.person_id,
        window_hours=int((datetime.now(UTC) - ws).total_seconds() / 3600) + 24,
        limit=500,
        offset=0,
    )
    signals = [s for s in signals if _in_window(s.get("fired_at"), ws, we)]

    signal_counts: dict[str, int] = {}
    highlights: list[dict] = []
    for s in signals:
        k = s.get("signal_type", "unknown")
        signal_counts[k] = signal_counts.get(k, 0) + 1
        if s.get("severity") in ("warning", "emergency"):
            highlights.append(
                {
                    "kind": k,
                    "fired_at": s.get("fired_at"),
                    "evidence_url": f"/cts/signals/{s.get('id')}/evidence",
                    "severity": s.get("severity"),
                }
            )

    highlights.sort(key=lambda h: (0 if h["severity"] == "emergency" else 1, str(h.get("fired_at", ""))), reverse=False)

    # Dwell totals from presence service
    dwell_by_room: list[dict] = []
    try:
        pls = getattr(request.app.state, "person_location_service", None)
        if pls is not None:
            segs = await pls.presence_history(body.person_id, ws, we)
            room_totals: dict[int, float] = {}
            room_names: dict[int, str] = {}
            for seg in segs:
                dur = ((seg.exited_at or min(we, datetime.now(UTC))) - max(seg.entered_at, ws)).total_seconds()
                if dur > 0:
                    room_totals[seg.room_id] = room_totals.get(seg.room_id, 0.0) + dur
                    room_names[seg.room_id] = str(seg.metadata.get("room_name", ""))
            dwell_by_room = [
                {"room_id": str(rid), "room_name": room_names.get(rid, ""), "minutes": round(total / 60, 1)}
                for rid, total in sorted(room_totals.items(), key=lambda x: x[1], reverse=True)
            ]
    except Exception:
        logger.exception("weekly_report_dwells_failed")

    return {
        "person_id": body.person_id,
        "week": {"start": ws.isoformat(), "end": we.isoformat()},
        "signal_counts": signal_counts,
        "dwell_by_room": dwell_by_room,
        "transitions": {"total": 0, "by_hour": []},
        "highlights": highlights,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _in_window(fired_at: str | None, ws: datetime, we: datetime) -> bool:
    if not fired_at:
        return False
    try:
        t = _parse_iso(fired_at)
        return ws <= t <= we
    except (ValueError, TypeError):
        return False
