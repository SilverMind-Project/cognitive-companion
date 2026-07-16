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

from backend.models.cts_signal import DementiaSignal
from backend.models.person import HouseholdMember, PersonLocationHistory, PersonLocationState
from backend.services.cts.identity_rewriter import IdentityRewriter
from backend.services.cts.signal_store import derive_signal_id


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


def _seed_history_row(
    db_factory,
    person_id: str,
    room: str,
    entered_at: datetime,
    *,
    ph_id: str = "ph-1",
    exited_at: datetime | None = None,
) -> None:
    db = db_factory()
    try:
        db.add(
            PersonLocationHistory(
                person_id=person_id,
                room_name=room,
                entered_at=entered_at,
                exited_at=exited_at,
                source="cts",
                ph_id=ph_id,
            )
        )
        db.commit()
    finally:
        db.close()


def _seed_state(db_factory, person_id: str, room: str, status: str = "home") -> None:
    db = db_factory()
    try:
        db.add(
            PersonLocationState(
                person_id=person_id,
                current_room_name=room,
                last_seen_at=datetime.now(UTC),
                last_sensor_id="cts",
                status=status,
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


class TestRangeScoping:
    """M06/F7: a revision touches exactly the rows its authority covers."""

    @pytest.mark.asyncio
    async def test_operator_range_supersedes_only_rows_inside_range(self, rewriter, db_factory):
        """Headline regression: 2 rows inside the range, 4 outside untouched."""
        base = datetime.now(UTC) - timedelta(hours=2)
        inside = [base + timedelta(minutes=12), base + timedelta(minutes=18)]
        outside = [
            base,
            base + timedelta(minutes=5),
            base + timedelta(minutes=25),
            base + timedelta(minutes=40),
        ]
        for t in inside + outside:
            _seed_history_row(db_factory, "grandma", "kitchen", t, ph_id="ph-range")

        revision = _revision(ph_id="ph-range")
        revision["revision_kind"] = "operator_correction"
        revision["range_start"] = (base + timedelta(minutes=10)).isoformat()
        revision["range_end"] = (base + timedelta(minutes=20)).isoformat()

        result = await rewriter.apply(revision)
        assert result["rewritten"] == 2
        assert result["inserted"] == 2

        db = db_factory()
        try:
            rows = (
                db.query(PersonLocationHistory)
                .filter(PersonLocationHistory.ph_id == "ph-range")
                .all()
            )
            superseded = [r for r in rows if r.superseded_by_revision_id is not None]
            live_originals = [
                r for r in rows if r.person_id == "grandma" and r.superseded_by_revision_id is None
            ]
            assert len(superseded) == 2
            assert len(live_originals) == 4
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_automatic_revision_bounded_by_horizon(self, db_factory):
        _seed_member(db_factory, "grandma")
        _seed_member(db_factory, "grandpa")
        rewriter = IdentityRewriter(
            db_factory=db_factory, ws_manager=None, revision_horizon_s=300.0
        )
        now = datetime.now(UTC)
        _seed_history_row(
            db_factory, "grandma", "kitchen", now - timedelta(seconds=100), ph_id="ph-auto"
        )
        _seed_history_row(
            db_factory, "grandma", "kitchen", now - timedelta(seconds=500), ph_id="ph-auto"
        )

        revision = _revision(ph_id="ph-auto")
        revision["revision_time"] = now.isoformat()
        result = await rewriter.apply(revision)

        assert result["rewritten"] == 1  # only the row inside the 300s horizon

    @pytest.mark.asyncio
    async def test_range_start_only_applies_lower_bound(self, rewriter, db_factory):
        base = datetime.now(UTC) - timedelta(hours=1)
        _seed_history_row(db_factory, "grandma", "kitchen", base, ph_id="ph-lo")
        _seed_history_row(
            db_factory, "grandma", "kitchen", base + timedelta(minutes=30), ph_id="ph-lo"
        )

        revision = _revision(ph_id="ph-lo")
        revision["range_start"] = (base + timedelta(minutes=10)).isoformat()
        result = await rewriter.apply(revision)
        assert result["rewritten"] == 1

    @pytest.mark.asyncio
    async def test_range_end_only_applies_upper_bound(self, rewriter, db_factory):
        base = datetime.now(UTC) - timedelta(hours=1)
        _seed_history_row(db_factory, "grandma", "kitchen", base, ph_id="ph-hi")
        _seed_history_row(
            db_factory, "grandma", "kitchen", base + timedelta(minutes=30), ph_id="ph-hi"
        )

        revision = _revision(ph_id="ph-hi")
        revision["range_end"] = (base + timedelta(minutes=10)).isoformat()
        result = await rewriter.apply(revision)
        assert result["rewritten"] == 1

    @pytest.mark.asyncio
    async def test_idempotent_replay_supersedes_nothing_new(self, rewriter, db_factory):
        base = datetime.now(UTC) - timedelta(hours=1)
        _seed_history_row(db_factory, "grandma", "kitchen", base, ph_id="ph-idem")

        revision = _revision(ph_id="ph-idem")
        revision["range_start"] = (base - timedelta(minutes=1)).isoformat()
        revision["range_end"] = (base + timedelta(minutes=1)).isoformat()

        first = await rewriter.apply(revision)
        assert first["rewritten"] == 1
        second = await rewriter.apply(revision)
        assert second["rewritten"] == 0


class TestLiveEdge:
    """M06: a purely historical correction must not flip current presence."""

    @pytest.mark.asyncio
    async def test_historical_correction_leaves_states_untouched(self, rewriter, db_factory):
        base = datetime.now(UTC) - timedelta(hours=3)
        _seed_history_row(
            db_factory,
            "grandma",
            "kitchen",
            base,
            ph_id="ph-hist",
            exited_at=base + timedelta(minutes=10),
        )
        # A newer, still-live row that the correction range does not reach.
        _seed_history_row(
            db_factory,
            "grandma",
            "living_room",
            datetime.now(UTC) - timedelta(minutes=5),
            ph_id="ph-hist",
        )
        _seed_state(db_factory, "grandma", "living_room")

        revision = _revision(ph_id="ph-hist")
        revision["range_start"] = (base - timedelta(minutes=1)).isoformat()
        revision["range_end"] = (base + timedelta(minutes=15)).isoformat()
        result = await rewriter.apply(revision)
        assert result["rewritten"] == 1

        db = db_factory()
        try:
            prior_state = (
                db.query(PersonLocationState)
                .filter(PersonLocationState.person_id == "grandma")
                .one()
            )
            assert prior_state.status == "home"
            new_state = (
                db.query(PersonLocationState)
                .filter(PersonLocationState.person_id == "grandpa")
                .first()
            )
            assert new_state is None
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_live_edge_correction_flips_presence(self, rewriter, db_factory):
        now = datetime.now(UTC)
        _seed_history_row(
            db_factory, "grandma", "kitchen", now - timedelta(minutes=5), ph_id="ph-live"
        )
        _seed_state(db_factory, "grandma", "kitchen")

        revision = _revision(ph_id="ph-live")
        revision["range_start"] = (now - timedelta(minutes=10)).isoformat()
        revision["range_end"] = now.isoformat()
        await rewriter.apply(revision)

        db = db_factory()
        try:
            prior_state = (
                db.query(PersonLocationState)
                .filter(PersonLocationState.person_id == "grandma")
                .one()
            )
            assert prior_state.status == "unknown"
            new_state = (
                db.query(PersonLocationState)
                .filter(PersonLocationState.person_id == "grandpa")
                .one()
            )
            assert new_state.status == "home"
            assert new_state.current_room_name == "kitchen"
        finally:
            db.close()


def _seed_signal(db_factory, person_id: str, window_start: datetime) -> None:
    db = db_factory()
    try:
        db.add(
            DementiaSignal(
                signal_id="sig-1",
                person_id=person_id,
                signal_type="pacing",
                severity="warning",
                window_start=window_start,
                window_end=window_start + timedelta(minutes=10),
                value=5.0,
            )
        )
        db.commit()
    finally:
        db.close()


class TestSignalSupersession:
    @pytest.mark.asyncio
    async def test_signal_superseded_and_recreated_under_new_identity(self, rewriter, db_factory):
        window = datetime.now(UTC) - timedelta(minutes=20)
        _seed_signal(db_factory, "grandma", window)
        revision = _revision()
        revision["revision_kind"] = "operator_correction"
        revision["range_start"] = (window - timedelta(minutes=1)).isoformat()
        revision["range_end"] = (window + timedelta(minutes=30)).isoformat()

        result = await rewriter.apply(revision)
        assert result["signals_superseded"] == 1

        db = db_factory()
        try:
            rows = db.query(DementiaSignal).all()
            assert len(rows) == 2  # original retained + replacement
            old = next(r for r in rows if r.person_id == "grandma")
            assert old.superseded_by_revision_id == "rev-1"
            new = next(r for r in rows if r.person_id == "grandpa")
            assert new.superseded_by_revision_id is None
            assert new.signal_type == "pacing"
            # F8: the replacement row re-derives its signal_id under the new
            # identity; it must never copy the superseded row's ID.
            assert new.signal_id != old.signal_id
            assert new.signal_id == derive_signal_id(
                "grandpa", "pacing", old.window_start.isoformat(), old.window_end.isoformat()
            )
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_signal_supersession_skipped_when_outside_horizon(self, rewriter, db_factory):
        # No explicit range: falls back to the default 600s horizon. This
        # signal's window is 20 minutes before revision_time, outside it.
        window = datetime.now(UTC) - timedelta(minutes=20)
        _seed_signal(db_factory, "grandma", window)
        result = await rewriter.apply(_revision())
        assert result["signals_superseded"] == 0

    @pytest.mark.asyncio
    async def test_signal_supersession_idempotent(self, rewriter, db_factory):
        window = datetime.now(UTC) - timedelta(minutes=20)
        _seed_signal(db_factory, "grandma", window)
        revision = _revision()
        revision["range_start"] = (window - timedelta(minutes=1)).isoformat()
        revision["range_end"] = (window + timedelta(minutes=30)).isoformat()
        first = await rewriter.apply(revision)
        assert first["signals_superseded"] == 1
        second = await rewriter.apply(revision)
        assert second["signals_superseded"] == 0

    @pytest.mark.asyncio
    async def test_signals_superseded_within_automatic_horizon(self, rewriter, db_factory):
        """M06 intended behavior change: automatic revisions (no explicit
        range) now supersede in-horizon signals, where previously the
        missing range short-circuited supersession entirely."""
        window = datetime.now(UTC) - timedelta(minutes=5)
        _seed_signal(db_factory, "grandma", window)
        result = await rewriter.apply(_revision())
        assert result["signals_superseded"] == 1
