"""Tests for IdentityRevisionSubscriber WS broadcast."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.services.cts.identity_revision_subscriber import IdentityRevisionSubscriber


@pytest.mark.asyncio
async def test_handle_broadcasts_cts_ph_correction_when_ws_manager_provided():
    ws_manager = AsyncMock()
    rewriter_mock = AsyncMock()
    rewriter_mock.apply.return_value = {"rewritten": 1}

    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter_mock,
        ws_manager=ws_manager,
    )
    revision = {
        "revision_id": "rev-1",
        "ph_id": "ph-1",
        "previous_identity_id": "alice",
        "new_identity_id": "bob",
        "reason": "manual_correct",
        "evidence": {},
        "revision_time": "2026-01-01T12:00:00Z",
    }
    result = await subscriber.handle(revision)
    assert result is True
    ws_manager.broadcast.assert_called_once()
    payload = ws_manager.broadcast.call_args.args[0]
    assert payload["type"] == "cts_ph_correction"
    assert payload["revision_id"] == "rev-1"
    assert payload["ph_id"] == "ph-1"


@pytest.mark.asyncio
async def test_handle_no_broadcast_when_ws_manager_is_none():
    rewriter_mock = AsyncMock()
    rewriter_mock.apply.return_value = {"rewritten": 0}
    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter_mock,
        ws_manager=None,
    )
    revision = {
        "revision_id": "rev-2",
        "ph_id": "ph-2",
        "previous_identity_id": None,
        "new_identity_id": "alice",
        "reason": "auto",
        "evidence": {},
        "revision_time": "2026-01-01T12:00:00Z",
    }
    result = await subscriber.handle(revision)
    assert result is True  # no crash
