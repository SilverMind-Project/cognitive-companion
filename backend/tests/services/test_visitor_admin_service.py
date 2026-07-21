"""Tests for :class:`VisitorAdminService` (identity-continuity M07).

The upstream face-service client is mocked (its own contract is covered by
``tests/integrations/test_person_id_client_visitors.py``); the household
member write goes through a real database session (testcontainer), per the
"never mock the database" testing standard, since the naming transaction's
create-or-recognize-existing branch is genuine query/write logic worth
proving against Postgres.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from backend.integrations.person_id_client import (
    PersonIDUpstreamError,
    VisitorClusterDetail,
    VisitorClusterListResult,
    VisitorClusterSummary,
    VisitorNameResult,
    VisitorSightingInfo,
)
from backend.models.person import HouseholdMember
from backend.services.visitors import VisitorAdminService, VisitorPartialFailureError

_NOW = datetime(2026, 7, 19, 10, 0, 0, tzinfo=UTC)


def _summary(**overrides) -> VisitorClusterSummary:
    base = {
        "cluster_id": "c1",
        "status": "surfaced",
        "display_hint": None,
        "named_person_id": None,
        "sighting_count": 4,
        "distinct_days": 3,
        "first_seen_at": _NOW,
        "last_seen_at": _NOW,
        "recent_crop_keys": ["visitor-crops/c1/1.jpg"],
    }
    base.update(overrides)
    return VisitorClusterSummary(**base)


def _presign(key):
    return f"https://minio/{key}" if key else None


class TestReads:
    async def test_list_clusters_presigns_crops(self):
        client = AsyncMock()
        client.list_visitor_clusters.return_value = VisitorClusterListResult(
            clusters=[_summary()], total=1
        )
        svc = VisitorAdminService(client)

        result = await svc.list_clusters(status="surfaced", presign=_presign)

        assert result.total == 1
        assert result.clusters[0].recent_crop_urls == ["https://minio/visitor-crops/c1/1.jpg"]
        client.list_visitor_clusters.assert_awaited_once_with("surfaced")

    async def test_list_clusters_without_presigner_omits_urls(self):
        client = AsyncMock()
        client.list_visitor_clusters.return_value = VisitorClusterListResult(
            clusters=[_summary()], total=1
        )
        svc = VisitorAdminService(client)

        result = await svc.list_clusters(status=None)

        assert result.clusters[0].recent_crop_urls == []

    async def test_get_cluster_maps_detail_and_sightings(self):
        client = AsyncMock()
        client.get_visitor_cluster.return_value = VisitorClusterDetail(
            cluster_id="c1",
            status="surfaced",
            display_hint=None,
            named_person_id=None,
            sighting_count=1,
            distinct_days=1,
            first_seen_at=_NOW,
            last_seen_at=_NOW,
            recent_crop_keys=[],
            recent_sightings=[VisitorSightingInfo(seen_at=_NOW, quality=0.9, crop_object="k1")],
        )
        svc = VisitorAdminService(client)

        result = await svc.get_cluster("c1", presign=_presign)

        assert result.cluster.cluster_id == "c1"
        assert result.recent_sightings[0].crop_url == "https://minio/k1"

    async def test_read_propagates_upstream_error(self):
        client = AsyncMock()
        client.list_visitor_clusters.side_effect = PersonIDUpstreamError(502, "boom")
        svc = VisitorAdminService(client)

        with pytest.raises(PersonIDUpstreamError):
            await svc.list_clusters(status=None)


class TestNamingTransaction:
    async def test_name_cluster_creates_household_member(self, db_session):
        client = AsyncMock()
        client.name_visitor_cluster.return_value = VisitorNameResult(
            cluster_id="c1",
            status="named",
            named_person_id="nurse-priya",
            member_name="Nurse Priya",
            embedding_count=5,
        )
        svc = VisitorAdminService(client)

        result = await svc.name_cluster(
            "c1", person_id="nurse-priya", name="Nurse Priya", db=db_session
        )

        assert result.household_member_created is True
        assert result.named_person_id == "nurse-priya"
        member = (
            db_session.query(HouseholdMember)
            .filter(HouseholdMember.id == "nurse-priya")
            .one()
        )
        assert member.name == "Nurse Priya"
        assert member.is_guest is True

    async def test_name_cluster_retry_after_cc_row_already_exists_is_idempotent(
        self, db_session
    ):
        """Simulates a retry where a prior attempt already created the CC row
        (e.g. the client received a network error after the write committed).
        The face-service call is idempotent per M06's 2026-07-21 rider, so this
        must succeed without a second insert or a conflict."""
        db_session.add(HouseholdMember(id="nurse-priya", name="Nurse Priya", is_guest=True))
        db_session.commit()

        client = AsyncMock()
        client.name_visitor_cluster.return_value = VisitorNameResult(
            cluster_id="c1",
            status="named",
            named_person_id="nurse-priya",
            member_name="Nurse Priya",
            embedding_count=5,
        )
        svc = VisitorAdminService(client)

        result = await svc.name_cluster(
            "c1", person_id="nurse-priya", name="Nurse Priya", db=db_session
        )

        assert result.household_member_created is False
        count = (
            db_session.query(HouseholdMember)
            .filter(HouseholdMember.id == "nurse-priya")
            .count()
        )
        assert count == 1

    async def test_name_cluster_propagates_upstream_error_before_any_cc_write(
        self, db_session
    ):
        client = AsyncMock()
        client.name_visitor_cluster.side_effect = PersonIDUpstreamError(
            409, "Visitor clustering is disabled"
        )
        svc = VisitorAdminService(client)

        with pytest.raises(PersonIDUpstreamError) as exc_info:
            await svc.name_cluster(
                "c1", person_id="nurse-priya", name="Nurse Priya", db=db_session
            )
        assert exc_info.value.status == 409
        assert db_session.query(HouseholdMember).count() == 0

    async def test_name_cluster_surfaces_partial_failure_when_cc_write_fails(
        self, db_session, monkeypatch
    ):
        client = AsyncMock()
        client.name_visitor_cluster.return_value = VisitorNameResult(
            cluster_id="c1",
            status="named",
            named_person_id="nurse-priya",
            member_name="Nurse Priya",
            embedding_count=5,
        )
        svc = VisitorAdminService(client)

        from sqlalchemy.exc import SQLAlchemyError

        def _boom(*_args, **_kwargs):
            raise SQLAlchemyError("connection lost")

        monkeypatch.setattr("backend.services.visitors.insert_household_member", _boom)

        with pytest.raises(VisitorPartialFailureError) as exc_info:
            await svc.name_cluster(
                "c1", person_id="nurse-priya", name="Nurse Priya", db=db_session
            )
        assert exc_info.value.person_id == "nurse-priya"


class TestDismissAndMerge:
    async def test_dismiss_cluster_calls_client(self):
        client = AsyncMock()
        svc = VisitorAdminService(client)

        result = await svc.dismiss_cluster("c1")

        assert result.cluster_id == "c1"
        assert result.status == "dismissed"
        client.dismiss_visitor_cluster.assert_awaited_once_with("c1")

    async def test_merge_clusters_presigns_result(self):
        client = AsyncMock()
        client.merge_visitor_clusters.return_value = _summary(cluster_id="c1")
        svc = VisitorAdminService(client)

        result = await svc.merge_clusters("c1", "c2", presign=_presign)

        assert result.cluster_id == "c1"
        assert result.recent_crop_urls == ["https://minio/visitor-crops/c1/1.jpg"]
