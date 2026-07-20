"""Unit tests for :class:`SignalRewriter`.

Verifies that applying an identity revision:
- supersedes matching DementiaSignal rows
- inserts parallel replacement rows under the new identity
- is idempotent when replayed
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.models.cts_signal import DementiaSignal
from backend.models.person import HouseholdMember
from backend.services.cts.signal_rewriter import SignalRewriter
from backend.services.cts.signal_store import derive_signal_id


def _seed_member(db_factory, person_id: str) -> None:
    db = db_factory()
    try:
        if db.get(HouseholdMember, person_id) is None:
            db.add(HouseholdMember(id=person_id, name=person_id.title()))
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
    return SignalRewriter(db_factory=db_factory, ws_manager=None)


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
        assert result.get("signals_superseded", 0) == 1

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
        assert result.get("signals_superseded", 0) == 0

    @pytest.mark.asyncio
    async def test_signal_supersession_idempotent(self, rewriter, db_factory):
        window = datetime.now(UTC) - timedelta(minutes=20)
        _seed_signal(db_factory, "grandma", window)
        revision = _revision()
        revision["range_start"] = (window - timedelta(minutes=1)).isoformat()
        revision["range_end"] = (window + timedelta(minutes=30)).isoformat()
        first = await rewriter.apply(revision)
        assert first.get("signals_superseded", 0) == 1
        second = await rewriter.apply(revision)
        assert second.get("signals_superseded", 0) == 0

    @pytest.mark.asyncio
    async def test_signals_superseded_within_automatic_horizon(self, rewriter, db_factory):
        """M06 intended behavior change: automatic revisions (no explicit
        range) now supersede in-horizon signals, where previously the
        missing range short-circuited supersession entirely."""
        window = datetime.now(UTC) - timedelta(minutes=5)
        _seed_signal(db_factory, "grandma", window)
        result = await rewriter.apply(_revision())
        assert result.get("signals_superseded", 0) == 1
