"""Unit tests for :class:`IdentityRewriter`.

Verifies that applying an identity revision:
- stamps the matching ``PersonLocationHistory`` rows with the revision id
- inserts parallel replacement rows under the new identity
- updates ``PersonLocationState`` for the new identity
- is idempotent when replayed
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.models.person import HouseholdMember, PersonLocationHistory, PersonLocationState
from backend.services.cts.identity_rewriter import IdentityRewriter


def _seed_member(db_factory, person_id: str) -> None:
    db = db_factory()
    try:
        if db.get(HouseholdMember, person_id) is None:
            db.add(HouseholdMember(id=person_id, name=person_id.title()))
            db.commit()
    finally:
        db.close()


def _seed_history(
    db_factory,
    person_id: str,
    room: str,
    ph_id: str = "ph-1",
) -> None:
    db = db_factory()
    try:
        now = datetime.now(UTC) - timedelta(minutes=5)
        db.add(
            PersonLocationHistory(
                person_id=person_id,
                room_name=room,
                entered_at=now,
                source="cts",
                ph_id=ph_id,
            )
        )
        db.add(
            PersonLocationState(
                person_id=person_id,
                current_room_name=room,
                last_seen_at=now,
                last_sensor_id="cts",
                status="home",
                confidence=0.9,
            )
        )
        db.commit()
    finally:
        db.close()


def _revision(
    *,
    revision_id: str = "rev-1",
    ph_id: str = "ph-1",
    previous_identity_id: str = "grandma",
    new_identity_id: str | None = "grandpa",
) -> dict:
    return {
        "revision_id": revision_id,
        "ph_id": ph_id,
        "previous_identity_id": previous_identity_id,
        "new_identity_id": new_identity_id,
        "map_identity_id": new_identity_id or "UNKNOWN",
        "posterior_entropy": 0.0,
        "reason": "manual",
        "evidence": {"actor": "test"},
        "revision_time": datetime.now(UTC).isoformat(),
    }


@pytest.fixture
def rewriter(db_factory):
    _seed_member(db_factory, "grandma")
    _seed_member(db_factory, "grandpa")
    return IdentityRewriter(db_factory=db_factory, ws_manager=None)


class TestRewrite:
    @pytest.mark.asyncio
    async def test_stamps_revision_id_and_inserts_new_row(self, rewriter, db_factory):
        _seed_history(db_factory, "grandma", "kitchen")
        result = await rewriter.apply(_revision())
        assert result["rewritten"] == 1
        assert result["inserted"] == 1

        db = db_factory()
        try:
            rows = db.query(PersonLocationHistory).all()
            assert len(rows) == 2
            prior = next(r for r in rows if r.person_id == "grandma")
            assert prior.superseded_by_revision_id == "rev-1"
            new = next(r for r in rows if r.person_id == "grandpa")
            assert new.room_name == "kitchen"
            assert new.source == "cts"
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_updates_new_identity_state(self, rewriter, db_factory):
        _seed_history(db_factory, "grandma", "kitchen")
        await rewriter.apply(_revision())

        db = db_factory()
        try:
            new_state = (
                db.query(PersonLocationState)
                .filter(PersonLocationState.person_id == "grandpa")
                .one()
            )
            assert new_state.current_room_name == "kitchen"
            assert new_state.status == "home"
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_is_idempotent(self, rewriter, db_factory):
        _seed_history(db_factory, "grandma", "kitchen")
        first = await rewriter.apply(_revision())
        assert first["rewritten"] == 1
        second = await rewriter.apply(_revision())
        # Second pass finds no rows without superseded_by_revision_id.
        assert second["rewritten"] == 0

    @pytest.mark.asyncio
    async def test_noop_when_previous_equals_new(self, rewriter, db_factory):
        _seed_history(db_factory, "grandma", "kitchen")
        result = await rewriter.apply(
            _revision(previous_identity_id="grandma", new_identity_id="grandma")
        )
        assert result["rewritten"] == 0
        assert result["inserted"] == 0

    @pytest.mark.asyncio
    async def test_clear_to_unknown_does_not_insert(self, rewriter, db_factory):
        _seed_history(db_factory, "grandma", "kitchen")
        result = await rewriter.apply(_revision(new_identity_id=None))
        assert result["rewritten"] == 1
        assert result["inserted"] == 0
