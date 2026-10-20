"""RosterHealthService: which members still need face enrollment, which visitors await review."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.integrations.person_id_client import (
    MemberInfo,
    PersonIDUpstreamError,
    VisitorClusterListResult,
)
from backend.models.person import HouseholdMember
from backend.services.identity_roster import RosterHealthService

_ENROLLED_AT = datetime(2026, 1, 1, tzinfo=UTC)


class _FakePersonID:
    """Person-identification answers for the two calls the service makes."""

    def __init__(
        self,
        embeddings: dict[str, int],
        surfaced_clusters: int = 0,
        visitors_error: PersonIDUpstreamError | None = None,
        members_error: PersonIDUpstreamError | None = None,
    ) -> None:
        self._embeddings = embeddings
        self._surfaced = surfaced_clusters
        self._visitors_error = visitors_error
        self._members_error = members_error
        self.cluster_status_requested: str | None = None

    async def list_members(self) -> list[MemberInfo]:
        if self._members_error is not None:
            raise self._members_error
        return [
            MemberInfo(person_id=pid, name=pid, embedding_count=n, created_at=_ENROLLED_AT)
            for pid, n in self._embeddings.items()
        ]

    async def list_visitor_clusters(self, status: str | None = None) -> VisitorClusterListResult:
        self.cluster_status_requested = status
        if self._visitors_error is not None:
            raise self._visitors_error
        return VisitorClusterListResult(clusters=[], total=self._surfaced)


@pytest.fixture
def members(db_factory):
    db = db_factory()
    db.add_all(
        [
            HouseholdMember(id="grandma", name="Grandma", is_active=True, is_guest=False),
            HouseholdMember(id="amma", name="Amma", is_active=True, is_guest=False),
            HouseholdMember(id="uncle", name="Uncle", is_active=True, is_guest=False),
            HouseholdMember(id="nurse", name="Nurse", is_active=True, is_guest=True),
            HouseholdMember(id="moved-out", name="Moved Out", is_active=False, is_guest=False),
        ]
    )
    db.commit()
    db.close()


def _service(client: _FakePersonID, db_factory, minimum: int = 5) -> RosterHealthService:
    return RosterHealthService(
        client,  # type: ignore[arg-type]
        session_factory=db_factory,
        min_face_embeddings=minimum,
    )


async def test_members_below_threshold_or_unenrolled_are_reported(db_factory, members) -> None:
    client = _FakePersonID({"grandma": 7, "amma": 3})

    health = await _service(client, db_factory).get_roster_health()

    assert [(m.member_id, m.embedding_count) for m in health.members_without_face_enrollment] == [
        ("amma", 3),
        ("uncle", 0),
    ]
    assert health.min_face_embeddings == 5
    assert health.is_complete is False


async def test_guests_and_inactive_members_are_never_reported(db_factory, members) -> None:
    client = _FakePersonID({"grandma": 5, "amma": 5, "uncle": 9})

    health = await _service(client, db_factory).get_roster_health()

    assert health.members_without_face_enrollment == []
    assert health.is_complete is True


async def test_surfaced_visitor_clusters_are_counted_and_block_completeness(
    db_factory, members
) -> None:
    client = _FakePersonID({"grandma": 5, "amma": 5, "uncle": 5}, surfaced_clusters=2)

    health = await _service(client, db_factory).get_roster_health()

    assert client.cluster_status_requested == "surfaced"
    assert health.surfaced_unnamed_visitor_clusters == 2
    assert health.visitor_clustering_enabled is True
    assert health.members_without_face_enrollment == []
    assert health.is_complete is False


async def test_disabled_visitor_clustering_counts_zero(db_factory, members) -> None:
    client = _FakePersonID(
        {"grandma": 5, "amma": 5, "uncle": 5},
        visitors_error=PersonIDUpstreamError(409, "Visitor clustering is disabled"),
    )

    health = await _service(client, db_factory).get_roster_health()

    assert health.visitor_clustering_enabled is False
    assert health.surfaced_unnamed_visitor_clusters == 0
    assert health.is_complete is True


@pytest.mark.parametrize(
    "client",
    [
        _FakePersonID({}, members_error=PersonIDUpstreamError(502, "unreachable")),
        _FakePersonID({"grandma": 5}, visitors_error=PersonIDUpstreamError(504, "timed out")),
    ],
    ids=["members_unreachable", "visitors_timeout"],
)
async def test_upstream_failure_raises_instead_of_reporting_a_roster(
    db_factory, members, client: _FakePersonID
) -> None:
    with pytest.raises(PersonIDUpstreamError):
        await _service(client, db_factory).get_roster_health()


def test_threshold_must_be_positive(db_factory) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        _service(_FakePersonID({}), db_factory, minimum=0)
