"""N5: Caregiver presence timeline API.

Provides presence segments, dwell totals, and current-location HUD data
backed by :class:`PersonLocationService`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.core.auth import require_permission
from backend.core.database import get_session
from backend.core.logging import get_logger
from backend.routers.cts_deps import cts_enabled
from backend.schemas.presence_timeline import (
    CurrentInEntry,
    CurrentlyInResponse,
    DwellsResponse,
    PresenceSegmentOut,
    RoomDwellTotal,
    RoomTransitionOut,
    SignalMarkerOut,
    TimelineResponse,
)
from backend.services.cts.signal_store import SignalStore

logger = get_logger(__name__)

router = APIRouter(prefix="/cts", tags=["cts-presence-timeline"])

_MAX_WINDOW_DAYS = 30
_DEFAULT_WINDOW_HOURS = 24


def _person_location(request: Request):
    svc = getattr(request.app.state, "person_location_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail={"code": "presence.unavailable"})
    return svc


# ---------------------------------------------------------------------------
# GET /presence/timeline/{person_id}
# ---------------------------------------------------------------------------


@router.get("/presence/timeline/{person_id}", response_model=TimelineResponse)
async def get_timeline(
    person_id: str,
    request: Request,
    since: str | None = Query(default=None, description="ISO-8601 start (default: 24h ago)"),
    until: str | None = Query(default=None, description="ISO-8601 end (default: now)"),
    _auth=Depends(require_permission("cts.presence.view")),
) -> TimelineResponse:
    cts_enabled()
    svc = _person_location(request)

    now = datetime.now(UTC)
    until_dt = _parse_iso(until) if until else now
    since_dt = _parse_iso(since) if since else until_dt - timedelta(hours=_DEFAULT_WINDOW_HOURS)

    if (until_dt - since_dt).days > _MAX_WINDOW_DAYS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "presence.window_too_large",
                "message": f"Window must not exceed {_MAX_WINDOW_DAYS} days",
            },
        )

    segments = await svc.presence_history(person_id, since_dt, until_dt)

    segment_outs = []
    transitions = []
    prev_room: int | None = None
    for seg in segments:
        seg_out = PresenceSegmentOut(
            segment_id=str(seg.id),
            person_id=seg.person_id,
            room_id=seg.room_id,
            room_name=str(seg.metadata.get("room_name", "")),
            entered_at=seg.entered_at,
            exited_at=seg.exited_at,
            dwell_seconds=((seg.exited_at or now) - seg.entered_at).total_seconds(),
            entry_source=seg.entry_source,
            exit_source=seg.exit_source,
            confidence=seg.confidence,
            is_open=seg.is_open,
            is_inferred=seg.is_inferred,
        )
        segment_outs.append(seg_out)

        if prev_room is not None and seg.room_id != prev_room:
            transitions.append(
                RoomTransitionOut(
                    from_room_id=prev_room,
                    from_room_name="",
                    to_room_id=seg.room_id,
                    to_room_name=str(seg.metadata.get("room_name", "")),
                    transitioned_at=seg.entered_at,
                    entry_source=seg.entry_source,
                )
            )
        prev_room = seg.room_id

    # Signal markers: per-person CTS dementia signals within the window.
    # SignalStore.list_recent anchors its lookback to *now*, so size the
    # window from now back to since_dt (until_dt is always <= now), then
    # post-filter to [since_dt, until_dt]. Sizing from (until-since) would
    # under-fetch for a window that ends in the past.
    signals: list[SignalMarkerOut] = []
    store = SignalStore(db_factory=get_session)
    sig_rows, _ = await store.list_recent(
        person_id=person_id,
        window_hours=max(1, int((now - since_dt).total_seconds() // 3600) + 1),
        limit=200,
    )
    for row in sig_rows:
        fired = _parse_iso(row["window_end"]) if row.get("window_end") else None
        if fired is not None and (fired < since_dt or fired > until_dt):
            continue
        signals.append(
            SignalMarkerOut(
                signal_id=str(row.get("signal_id") or row.get("id")),
                signal_kind=str(row.get("signal_type", "")),
                severity=str(row.get("severity", "info")),
                fired_at=fired,
            )
        )

    return TimelineResponse(
        person_id=person_id,
        since=since_dt,
        until=until_dt,
        segments=sorted(segment_outs, key=lambda s: s.entered_at or now),
        transitions=transitions,
        signals=signals,
    )


# ---------------------------------------------------------------------------
# GET /presence/dwells/{person_id}
# ---------------------------------------------------------------------------


@router.get("/presence/dwells/{person_id}", response_model=DwellsResponse)
async def get_dwells(
    person_id: str,
    request: Request,
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    _auth=Depends(require_permission("cts.presence.view")),
) -> DwellsResponse:
    cts_enabled()
    svc = _person_location(request)

    now = datetime.now(UTC)
    until_dt = _parse_iso(until) if until else now
    since_dt = _parse_iso(since) if since else until_dt - timedelta(hours=_DEFAULT_WINDOW_HOURS)

    segments = await svc.presence_history(person_id, since_dt, until_dt)

    by_room: dict[int, float] = {}
    room_names: dict[int, str] = {}
    for seg in segments:
        dur = ((seg.exited_at or now) - seg.entered_at).total_seconds()
        by_room[seg.room_id] = by_room.get(seg.room_id, 0.0) + dur
        room_names[seg.room_id] = str(seg.metadata.get("room_name", ""))

    dwells = [
        RoomDwellTotal(room_id=rid, room_name=room_names.get(rid, ""), total_seconds=total)
        for rid, total in sorted(by_room.items(), key=lambda x: x[1], reverse=True)
    ]

    return DwellsResponse(
        person_id=person_id,
        window_since=since_dt,
        window_until=until_dt,
        dwells=dwells,
    )


# ---------------------------------------------------------------------------
# GET /presence/currently_in
# ---------------------------------------------------------------------------


@router.get("/presence/currently_in", response_model=CurrentlyInResponse)
async def get_currently_in(
    request: Request,
    _auth=Depends(require_permission("cts.presence.view")),
) -> CurrentlyInResponse:
    cts_enabled()
    svc = _person_location(request)

    now = datetime.now(UTC)
    members = getattr(request.app.state, "household_members", [])
    if not members:
        try:
            from backend.core.database import get_session
            from backend.models.person import HouseholdMember

            db = get_session()
            try:
                members = db.query(HouseholdMember).filter(HouseholdMember.is_active == True).all()  # noqa: E712
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            members = []

    entries: list[CurrentInEntry] = []
    for member in members:
        person_id = getattr(member, "id", None) or getattr(member, "person_id", None) or ""
        display_name = getattr(member, "display_name", "") or getattr(member, "name", "") or ""
        loc = await svc.where_is(str(person_id))
        if loc is not None:
            entries.append(
                CurrentInEntry(
                    person_id=loc.person_id,
                    display_name=display_name,
                    room_id=loc.room_id,
                    room_name=loc.room_name,
                    since=loc.since,
                    dwell_seconds=(now - loc.since).total_seconds() if loc.since else 0.0,
                    entry_source=loc.entry_source,
                    is_inferred=loc.is_inferred,
                    last_observed_at=loc.since,
                )
            )
        else:
            entries.append(
                CurrentInEntry(
                    person_id=str(person_id),
                    display_name=display_name,
                    room_id=None,
                    room_name=None,
                    since=None,
                    dwell_seconds=0.0,
                    entry_source=None,
                    is_inferred=False,
                )
            )

    return CurrentlyInResponse(occupants=entries)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt
