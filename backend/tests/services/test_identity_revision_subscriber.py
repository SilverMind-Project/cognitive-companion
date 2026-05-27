"""Unit tests for :class:`IdentityRevisionSubscriber` (proto wire format)."""

from __future__ import annotations

import json

import pytest

from backend.integrations.proto.continuoustracking.v1 import (  # type: ignore[attr-defined]
    tracking_pb2,
)
from backend.services.cts.identity_revision_subscriber import IdentityRevisionSubscriber


def _payload(**overrides) -> dict[bytes, bytes]:
    defaults = {
        "revision_id": "rev-1",
        "ph_id": "ph-1",
        "previous_identity_id": "grandma",
        "new_identity_id": "grandpa",
        "reason": "manual",
        "evidence_json": json.dumps({"actor": "tester"}),
        "revision_time_unix_ns": 1735305600000000000,
    }
    defaults.update(overrides)
    msg = tracking_pb2.IdentityRevision(**defaults)
    return {b"revision": msg.SerializeToString()}


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
        assert rev["ph_id"] == "ph-1"
        assert rev["previous_identity_id"] == "grandma"
        assert rev["new_identity_id"] == "grandpa"
        assert rev["evidence"] == {"actor": "tester"}

    def test_rejects_missing_required_fields(self, subscriber):
        sub, _ = subscriber
        # revision_id is required; an empty one drops the message.
        assert sub.decode(b"0-0", _payload(revision_id="")) is None

    def test_empty_string_new_identity_becomes_none(self, subscriber):
        sub, _ = subscriber
        rev = sub.decode(b"0-0", _payload(new_identity_id=""))
        assert rev is not None
        assert rev["new_identity_id"] is None

    def test_missing_payload_returns_none(self, subscriber):
        sub, _ = subscriber
        assert sub.decode(b"0-0", {}) is None

    def test_garbage_payload_returns_none(self, subscriber):
        sub, _ = subscriber
        assert sub.decode(b"0-0", {b"revision": b"not-protobuf-\xff\x01"}) is None


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
