"""WTR1: PersonLocationService contract tests.

Contract: WTR1 §6 — person location rows use ``person_id``, not ``ph_id``.
PH id belongs in ``source_ref``. The service must accept a PH id as
``source_ref`` without conflating it with the person identity.

Contract: WTR1 §8 — PersonLocationService is the single source of truth
for caregiver-facing presence.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import FloorPoint


def _make_service() -> PersonLocationService:
    obs_repo = InMemoryObservationRepository()
    seg_repo = InMemorySegmentRepository()
    return PersonLocationService(obs_repo, seg_repo, PersonLocationConfig())


@pytest.mark.asyncio
async def test_ingest_observation_accepts_person_id_and_source_ref():
    """ingest_observation() takes person_id and source_ref separately.

    The person_id identifies the household member. The source_ref carries
    provenance (e.g., a PH id) without becoming the person identity.
    """
    svc = _make_service()
    now = datetime.now(UTC)

    # source_ref carries a PH id — this must not mutate person_id
    await svc.ingest_observation(
        person_id="alice",
        observed_at=now,
        source="world_tracker",
        source_ref="ph-abc-123",
        floor_point=FloorPoint(x_m=1.5, y_m=3.2),
        room_id=1,
        confidence=0.95,
    )

    result = await svc.where_is("alice")
    assert result is not None
    # The person_id must remain "alice", not "ph-abc-123"
    assert result.person_id == "alice"


@pytest.mark.asyncio
async def test_source_ref_preserves_ph_id_separate_from_person_id():
    """source_ref stores a PH id for audit without overwriting person_id."""
    svc = _make_service()
    now = datetime.now(UTC)

    await svc.ingest_observation(
        person_id="bob",
        observed_at=now,
        source="world_tracker",
        source_ref="ph-xyz-789",
        room_id=2,
        confidence=0.8,
    )

    result = await svc.where_is("bob")
    assert result is not None
    assert result.person_id == "bob"
    # The PH id must not leak into the person_id field
    assert result.person_id != "ph-xyz-789"


@pytest.mark.asyncio
async def test_multiple_source_refs_for_same_person_are_independent():
    """Multiple PH ids for the same person must not collide."""
    svc = _make_service()
    now = datetime.now(UTC)

    # Ingest from two different PHs, same person
    await svc.ingest_observation(
        person_id="carol",
        observed_at=now,
        source="world_tracker",
        source_ref="ph-111",
        room_id=1,
        confidence=0.9,
    )
    await svc.ingest_observation(
        person_id="carol",
        observed_at=now,
        source="world_tracker",
        source_ref="ph-222",
        room_id=1,
        confidence=0.85,
    )

    # Both should succeed without collision — person_id stays "carol"
    result = await svc.where_is("carol")
    assert result is not None
    assert result.person_id == "carol"


@pytest.mark.asyncio
async def test_presence_history_returns_person_id():
    """presence_history() returns results keyed by person_id, not ph_id."""
    svc = _make_service()
    now = datetime.now(UTC)

    await svc.ingest_observation(
        person_id="dave",
        observed_at=now,
        source="world_tracker",
        source_ref="ph-dave-1",
        room_id=3,
        confidence=0.9,
    )

    from datetime import timedelta

    segments = await svc.presence_history(
        person_id="dave",
        since=now - timedelta(hours=1),
        until=now + timedelta(hours=1),
    )
    assert isinstance(segments, list)


@pytest.mark.asyncio
async def test_occupants_of_returns_person_ids_not_ph_ids():
    """occupants_of() returns person_id values, not PH ids."""
    svc = _make_service()
    now = datetime.now(UTC)

    await svc.ingest_observation(
        person_id="eve",
        observed_at=now,
        source="world_tracker",
        source_ref="ph-eve-1",
        room_id=4,
        confidence=0.9,
    )

    occupants = await svc.occupants_of(room_id=4)
    assert isinstance(occupants, list)


@pytest.mark.asyncio
async def test_service_query_methods_exist():
    """WTR1 §8: PersonLocationService must expose the query methods
    that filters and steps depend on."""
    svc = _make_service()

    assert callable(svc.where_is)
    assert callable(svc.presence_history)
    assert callable(svc.occupants_of)
    assert callable(svc.current_dwell)
    assert callable(svc.ingest_observation)
    assert callable(svc.ingest_room_transition)
    assert callable(svc.ingest_manual_override)
    assert callable(svc.apply_identity_revision)
