"""Roster health: who still needs face enrollment, and which visitors await review.

One service method powers both the BFF route (``GET /api/v1/persons/roster-health``) and the
``get_roster_health`` MCP tool.

Upstream failures raise ``PersonIDUpstreamError`` rather than degrading to an empty roster: an
unreachable face service must never be reported as "everyone is enrolled" or "nobody is".
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.integrations.person_id_client import PersonIDClient, PersonIDUpstreamError
from backend.models.person import HouseholdMember
from backend.schemas.identity_roster import RosterHealthEnvelope, RosterMemberRef

# person-identification-service answers 409 for visitor endpoints when clustering is disabled.
_CLUSTERING_DISABLED_STATUS = 409


class RosterHealthService:
    def __init__(
        self,
        client: PersonIDClient,
        session_factory: Callable[[], Session],
        min_face_embeddings: int,
    ) -> None:
        if min_face_embeddings < 1:
            raise ValueError("min_face_embeddings must be at least 1")
        self._client = client
        self._session_factory = session_factory
        self._min_face_embeddings = min_face_embeddings

    async def get_roster_health(self) -> RosterHealthEnvelope:
        enrolled = {m.person_id: m.embedding_count for m in await self._client.list_members()}
        clustering_enabled, surfaced = await self._surfaced_visitor_clusters()

        missing = [
            RosterMemberRef(member_id=member_id, name=name, embedding_count=count)
            for member_id, name in self._active_resident_members()
            if (count := enrolled.get(member_id, 0)) < self._min_face_embeddings
        ]
        return RosterHealthEnvelope(
            members_without_face_enrollment=missing,
            min_face_embeddings=self._min_face_embeddings,
            visitor_clustering_enabled=clustering_enabled,
            surfaced_unnamed_visitor_clusters=surfaced,
            is_complete=not missing and surfaced == 0,
            checked_at=datetime.now(UTC),
        )

    def _active_resident_members(self) -> list[tuple[str, str]]:
        db = self._session_factory()
        try:
            rows = (
                db.query(HouseholdMember.id, HouseholdMember.name)
                .filter(HouseholdMember.is_active.is_(True), HouseholdMember.is_guest.is_(False))
                .order_by(HouseholdMember.name)
                .all()
            )
            return [(row.id, row.name) for row in rows]
        finally:
            db.close()

    async def _surfaced_visitor_clusters(self) -> tuple[bool, int]:
        try:
            result = await self._client.list_visitor_clusters("surfaced")
        except PersonIDUpstreamError as exc:
            if exc.status == _CLUSTERING_DISABLED_STATUS:
                return False, 0
            raise
        return True, result.total
