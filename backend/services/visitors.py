"""BFF service for the visitor cluster admin surface (identity-continuity M07).

One service function powers each thin route in ``routers/visitors.py`` (D6:
the same function backs the browser router; there is no MCP tool for the
mutation routes, see the exemption test in ``tests/routers/test_visitors.py``).

Naming a cluster is a two-system transaction: create the member in
person-identification-service, then create the matching ``household_members``
row in Cognitive Companion (``is_guest=True``). If step two fails after step
one already committed, the caller must retry safely: M06 was extended
(2026-07-21 dated rider, see the M06 milestone doc) so re-naming a cluster
already named to the same ``person_id`` returns success rather than a 409, so
this service's retry-on-partial-failure story actually works end to end.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.integrations.person_id_client import (
    PersonIDClient,
    PersonIDUpstreamError,
    VisitorClusterDetail,
    VisitorClusterSummary,
)
from backend.models.person import HouseholdMember
from backend.schemas.visitors import (
    DismissVisitorResponse,
    NameVisitorResponse,
    VisitorClusterDetailView,
    VisitorClusterListResponse,
    VisitorClusterView,
    VisitorSightingView,
)
from backend.services.persons import insert_household_member

logger = logging.getLogger(__name__)

# Presign callable: maps a MinIO key (or None) to a URL (or None).
Presigner = Callable[[str | None], str | None]


def _no_presign(_key: str | None) -> str | None:
    return None


class VisitorPartialFailureError(Exception):
    """The face-service member was created but the CC household member insert
    failed. The face-service naming call is idempotent on ``person_id`` (M06's
    2026-07-21 rider), so retrying this same request is safe and will not
    re-create the face-service member or double-spend embeddings."""

    def __init__(self, person_id: str, name: str) -> None:
        self.person_id = person_id
        self.name = name
        super().__init__(
            f"Visitor '{person_id}' was named in the face service, but saving the "
            "household member record failed. Retrying is safe."
        )


class VisitorAdminService:
    """Compose browser-facing visitor review responses from the face service."""

    def __init__(self, client: PersonIDClient) -> None:
        self._client = client

    # -- reads ------------------------------------------------------------

    async def list_clusters(
        self, *, status: str | None, presign: Presigner = _no_presign
    ) -> VisitorClusterListResponse:
        result = await self._client.list_visitor_clusters(status)
        return VisitorClusterListResponse(
            clusters=[self._view(c, presign) for c in result.clusters],
            total=result.total,
        )

    async def get_cluster(
        self, cluster_id: str, *, presign: Presigner = _no_presign
    ) -> VisitorClusterDetailView:
        detail = await self._client.get_visitor_cluster(cluster_id)
        return VisitorClusterDetailView(
            cluster=self._view(detail, presign),
            recent_sightings=[
                VisitorSightingView(
                    seen_at=s.seen_at,
                    quality=s.quality,
                    crop_object=s.crop_object,
                    crop_url=presign(s.crop_object),
                )
                for s in detail.recent_sightings
            ],
        )

    # -- mutations ----------------------------------------------------------

    async def name_cluster(
        self, cluster_id: str, *, person_id: str, name: str, db: Session
    ) -> NameVisitorResponse:
        # Step 1: the privileged transition. Moves biometric data from the
        # visitor dataset into the governed enrollment dataset.
        result = await self._client.name_visitor_cluster(cluster_id, person_id, name)

        # Step 2: create (or, on a safe retry, recognize) the CC household
        # member. Idempotent by construction: if a prior attempt already
        # created this row, do not insert a second time or raise a conflict.
        existing = db.query(HouseholdMember).filter(HouseholdMember.id == person_id).first()
        created = False
        if existing is None:
            try:
                insert_household_member(db, id=person_id, name=result.member_name, is_guest=True)
                created = True
            except SQLAlchemyError as exc:
                logger.exception(
                    "visitor_household_member_creation_failed",
                    extra={"person_id": person_id, "cluster_id": cluster_id},
                )
                raise VisitorPartialFailureError(person_id, result.member_name) from exc

        return NameVisitorResponse(
            cluster_id=result.cluster_id,
            status=result.status,
            named_person_id=result.named_person_id,
            member_name=result.member_name,
            embedding_count=result.embedding_count,
            household_member_created=created,
        )

    async def dismiss_cluster(self, cluster_id: str) -> DismissVisitorResponse:
        await self._client.dismiss_visitor_cluster(cluster_id)
        return DismissVisitorResponse(cluster_id=cluster_id, status="dismissed")

    async def merge_clusters(
        self, cluster_a: str, cluster_b: str, *, presign: Presigner = _no_presign
    ) -> VisitorClusterView:
        merged = await self._client.merge_visitor_clusters(cluster_a, cluster_b)
        return self._view(merged, presign)

    # -- internals ------------------------------------------------------------

    @staticmethod
    def _view(
        cluster: VisitorClusterSummary | VisitorClusterDetail, presign: Presigner
    ) -> VisitorClusterView:
        return VisitorClusterView(
            cluster_id=cluster.cluster_id,
            status=cluster.status,
            display_hint=cluster.display_hint,
            named_person_id=cluster.named_person_id,
            sighting_count=cluster.sighting_count,
            distinct_days=cluster.distinct_days,
            first_seen_at=cluster.first_seen_at,
            last_seen_at=cluster.last_seen_at,
            recent_crop_urls=[
                url for key in cluster.recent_crop_keys if (url := presign(key)) is not None
            ],
        )


__all__ = ["PersonIDUpstreamError", "VisitorAdminService", "VisitorPartialFailureError"]
