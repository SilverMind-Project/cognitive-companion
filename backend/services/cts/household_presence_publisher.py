"""Publishes household presence and roster completeness to ``cc.household_presence``.

Fuses per-member presence from :class:`PresenceService`, roster completeness
from :class:`RosterHealthService`, and active visitor detection from
:class:`OccupancyReadModel` / named guests / recent surfaced visitor clusters,
then emits raw protobuf :class:`HouseholdPresence` messages (field
``"presence"``) on any state change and at least once every 60 seconds.

Fails closed on face-service outages: if ``RosterHealthService`` raises
``PersonIDUpstreamError``, publishes ``roster_complete = False`` so CTS keeps
its closed-world channel inactive instead of reasoning over an unverified roster.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cts_contracts.household import PresenceStatus

from backend.core.logging import get_logger
from backend.integrations.person_id_client import PersonIDUpstreamError
from backend.integrations.proto.continuoustracking.v1 import household_pb2
from backend.models.person import HouseholdMember
from backend.services.cts._types import DBSessionFactory
from backend.services.identity_roster import RosterHealthService
from backend.services.occupancy.read_model import OccupancyReadModel
from backend.services.presence.service import PresenceService

logger = get_logger(__name__)

STREAM = "cc.household_presence"
FIELD_PRESENCE = b"presence"
_MAX_STREAM_LEN = 1000

_PRESENT_GUEST_STATUSES: frozenset[PresenceStatus] = frozenset(
    {
        PresenceStatus.PRESENT_ROOM,
        PresenceStatus.PRESENT_HOME,
        PresenceStatus.ASLEEP,
    }
)

_PRESENCE_STATUS_TO_PROTO: dict[PresenceStatus, int] = {
    PresenceStatus.PRESENT_ROOM: household_pb2.PRESENCE_STATUS_PRESENT_ROOM,
    PresenceStatus.PRESENT_HOME: household_pb2.PRESENCE_STATUS_PRESENT_HOME,
    PresenceStatus.AWAY: household_pb2.PRESENCE_STATUS_AWAY,
    PresenceStatus.ASLEEP: household_pb2.PRESENCE_STATUS_ASLEEP,
    PresenceStatus.UNKNOWN: household_pb2.PRESENCE_STATUS_UNKNOWN,
    PresenceStatus.STALE: household_pb2.PRESENCE_STATUS_STALE,
}


@dataclass(frozen=True)
class _PublishFingerprint:
    """Normalized state key used to detect meaningful presence/roster changes."""

    members: tuple[tuple[str, str, float, str], ...]
    roster_complete: bool
    visitors_present: bool


class HouseholdPresencePublisher:
    """Publishes ``HouseholdPresence`` snapshots to ``cc.household_presence``."""

    def __init__(
        self,
        *,
        redis_client: Any,
        presence_service: PresenceService,
        roster_health_service: RosterHealthService,
        db_factory: DBSessionFactory,
        occupancy_read_model: OccupancyReadModel | None = None,
        stream: str = STREAM,
        poll_interval_s: float = 5.0,
        heartbeat_interval_s: float = 60.0,
        visitor_sighting_window_s: float = 3600.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if poll_interval_s <= 0.0:
            raise ValueError("poll_interval_s must be positive")
        if heartbeat_interval_s <= 0.0:
            raise ValueError("heartbeat_interval_s must be positive")
        if visitor_sighting_window_s <= 0.0:
            raise ValueError("visitor_sighting_window_s must be positive")
        self._redis = redis_client
        self._presence = presence_service
        self._roster_health = roster_health_service
        self._db_factory = db_factory
        self._occupancy = occupancy_read_model
        self._stream = stream
        self._poll_interval_s = poll_interval_s
        self._heartbeat_interval_s = heartbeat_interval_s
        self._visitor_sighting_window_s = visitor_sighting_window_s
        self._clock = clock
        self._last_fingerprint: _PublishFingerprint | None = None
        self._last_published_at: datetime | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start periodic change-and-heartbeat publishing in the background."""
        self._running = True
        self._task = asyncio.create_task(
            self._run_loop(),
            name="household-presence-publisher",
        )
        logger.info(
            "household_presence_publisher_started",
            stream=self._stream,
            poll_interval_s=self._poll_interval_s,
            heartbeat_interval_s=self._heartbeat_interval_s,
        )

    async def stop(self) -> None:
        """Stop the background publish loop cleanly."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("household_presence_publisher_stopped", stream=self._stream)

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.publish_if_due()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("household_presence_publish_tick_failed", stream=self._stream)
            await asyncio.sleep(self._poll_interval_s)

    def _load_active_member_ids(self) -> tuple[list[str], list[str]]:
        """Return sorted ``(resident_ids, named_guest_ids)`` for active household members."""
        db = self._db_factory()
        try:
            rows = (
                db.query(HouseholdMember.id, HouseholdMember.is_guest)
                .filter(HouseholdMember.is_active.is_(True))
                .order_by(HouseholdMember.id)
                .all()
            )
            residents = [str(row.id) for row in rows if not row.is_guest]
            guests = [str(row.id) for row in rows if row.is_guest]
            return residents, guests
        finally:
            db.close()

    async def build_message(
        self,
        *,
        at: datetime | None = None,
    ) -> tuple[household_pb2.HouseholdPresence, _PublishFingerprint]:
        """Collect current presence, roster completeness, and visitor state."""
        now = at or self._clock()
        resident_ids, guest_ids = self._load_active_member_ids()

        proto_members: list[household_pb2.MemberPresence] = []
        fp_members: list[tuple[str, str, float, str]] = []
        for member_id in resident_ids:
            snap = await self._presence.get(member_id, at=now)
            proto_status = _PRESENCE_STATUS_TO_PROTO.get(
                snap.status, household_pb2.PRESENCE_STATUS_UNKNOWN
            )
            room_id = snap.room_id or ""
            confidence = max(0.0, min(1.0, float(snap.confidence)))
            inferred_ns = int(snap.inferred_at.timestamp() * 1e9)
            proto_members.append(
                household_pb2.MemberPresence(
                    member_id=member_id,
                    status=proto_status,
                    confidence=confidence,
                    room_id=room_id,
                    inferred_at_unix_ns=inferred_ns,
                )
            )
            fp_members.append((member_id, str(snap.status), round(confidence, 3), room_id))

        roster_complete = False
        recent_surfaced_visitor = False
        try:
            health = await self._roster_health.get_roster_health()
            roster_complete = bool(health.is_complete)
            if health.surfaced_unnamed_visitor_clusters > 0:
                recent_surfaced_visitor = await self._roster_health.has_recent_surfaced_visitor(
                    within_s=self._visitor_sighting_window_s,
                    now=now,
                )
        except PersonIDUpstreamError as exc:
            logger.warning(
                "household_presence_roster_health_unavailable",
                status=exc.status,
                detail=str(exc),
            )
            roster_complete = False

        named_guest_present = await self._is_named_guest_present(guest_ids, now=now)
        visitors_present = bool(recent_surfaced_visitor or named_guest_present)

        msg = household_pb2.HouseholdPresence(
            members=proto_members,
            roster_complete=roster_complete,
            visitors_present=visitors_present,
            published_at_unix_ns=int(now.timestamp() * 1e9),
        )
        fingerprint = _PublishFingerprint(
            members=tuple(fp_members),
            roster_complete=roster_complete,
            visitors_present=visitors_present,
        )
        return msg, fingerprint

    async def _is_named_guest_present(self, guest_ids: list[str], *, now: datetime) -> bool:
        if not guest_ids:
            return False
        guest_set = set(guest_ids)
        if self._occupancy is not None:
            for room in await self._occupancy.get_occupancy():
                if guest_set.intersection(room.person_ids):
                    return True
        for guest_id in guest_ids:
            snap = await self._presence.get(guest_id, at=now)
            if snap.status in _PRESENT_GUEST_STATUSES:
                return True
        return False

    async def publish_if_due(self, *, force: bool = False) -> bool:
        """Publish to Redis if state changed, heartbeat elapsed, or *force* is True."""
        now = self._clock()
        msg, fingerprint = await self.build_message(at=now)
        changed = fingerprint != self._last_fingerprint
        heartbeat_due = (
            self._last_published_at is None
            or (now - self._last_published_at).total_seconds() >= self._heartbeat_interval_s
        )
        if not (force or changed or heartbeat_due):
            return False

        fields = {FIELD_PRESENCE: msg.SerializeToString()}
        await self._redis.xadd(
            self._stream,
            fields,
            maxlen=_MAX_STREAM_LEN,
            approximate=True,
        )
        self._last_fingerprint = fingerprint
        self._last_published_at = now
        logger.debug(
            "household_presence_published",
            stream=self._stream,
            member_count=len(msg.members),
            roster_complete=msg.roster_complete,
            visitors_present=msg.visitors_present,
            changed=changed,
        )
        return True
