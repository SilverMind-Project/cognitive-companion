"""Unit tests for :class:`IdentityRevisionSubscriber`."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from backend.services.cts.identity_revision_subscriber import IdentityRevisionSubscriber


def _payload(overrides: dict[bytes, bytes] | None = None) -> dict[bytes, bytes]:
    base = {
        b"revision_id": b"rev-1",
        b"global_track_id": b"gt-1",
        b"tracklet_ids": json.dumps(["t-1", "t-2"]).encode(),
        b"previous_identity_id": b"grandma",
        b"new_identity_id": b"grandpa",
        b"map_identity_id": b"grandpa",
        b"posterior_entropy": b"0.0",
        b"reason": b"manual",
        b"evidence": json.dumps({"actor": "tester"}).encode(),
        b"revision_time": datetime.now(UTC).isoformat().encode(),
    }
    if overrides:
        base.update(overrides)
    return base


class _StubRewriter:
    def __init__(self) -> None:
        self.applied: list[dict] = []

    async def apply(self, revision: dict) -> dict:
        self.applied.append(revision)
        return {"revision_id": revision["revision_id"], "rewritten": 1, "inserted": 1}


@pytest.fixture
def subscriber():
    rewriter = _StubRewriter()
    sub = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter,  # type: ignore[arg-type]
        pipeline=None,
    )
    return sub, rewriter


class TestDecode:
    def test_parses_all_fields(self, subscriber):
        sub, _ = subscriber
        rev = sub.decode(b"0-0", _payload())
        assert rev is not None
        assert rev["revision_id"] == "rev-1"
        assert rev["tracklet_ids"] == ["t-1", "t-2"]
        assert rev["previous_identity_id"] == "grandma"
        assert rev["new_identity_id"] == "grandpa"
        assert rev["evidence"] == {"actor": "tester"}

    def test_rejects_missing_required_fields(self, subscriber):
        sub, _ = subscriber
        fields = _payload()
        del fields[b"revision_time"]
        assert sub.decode(b"0-0", fields) is None

    def test_empty_string_new_identity_becomes_none(self, subscriber):
        sub, _ = subscriber
        rev = sub.decode(b"0-0", _payload(overrides={b"new_identity_id": b""}))
        assert rev is not None
        assert rev["new_identity_id"] is None


class TestHandle:
    @pytest.mark.asyncio
    async def test_delegates_to_rewriter(self, subscriber):
        sub, rewriter = subscriber
        rev = sub.decode(b"0-0", _payload())
        assert rev is not None
        ok = await sub.handle(rev)
        assert ok is True
        assert rewriter.applied
        assert rewriter.applied[0]["revision_id"] == "rev-1"
