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


@pytest.mark.asyncio
async def test_handle_posts_projection_ack_when_cc_required():
    """M06: a revision requiring the cc projection acks back to CTS on success."""
    rewriter_mock = AsyncMock()
    rewriter_mock.apply.return_value = {"rewritten": 3, "inserted": 3}
    orchestrator = AsyncMock()

    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter_mock,
        orchestrator_client=orchestrator,
    )
    revision = {
        "revision_id": "rev-ack",
        "ph_id": "ph-1",
        "previous_identity_id": "alice",
        "new_identity_id": "bob",
        "reason": "operator_correction",
        "evidence": {},
        "revision_time": "2026-06-20T12:00:00Z",
        "required_projections": ["cts_internal", "cc"],
        "revision_schema_version": "1",
    }
    result = await subscriber.handle(revision)
    assert result is True
    orchestrator.post_projection_ack.assert_called_once()
    kwargs = orchestrator.post_projection_ack.call_args.kwargs
    assert kwargs["revision_id"] == "rev-ack"
    assert kwargs["consumer"] == "cc"
    assert kwargs["status"] == "acked"
    assert kwargs["counts"] == {"rewritten": 3, "inserted": 3}


@pytest.mark.asyncio
async def test_handle_skips_ack_for_legacy_revision_without_required_projections():
    rewriter_mock = AsyncMock()
    rewriter_mock.apply.return_value = {"rewritten": 1}
    orchestrator = AsyncMock()

    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter_mock,
        orchestrator_client=orchestrator,
    )
    revision = {
        "revision_id": "rev-legacy",
        "ph_id": "ph-1",
        "previous_identity_id": None,
        "new_identity_id": "alice",
        "reason": "auto",
        "evidence": {},
        "revision_time": "2026-06-20T12:00:00Z",
        "required_projections": [],
    }
    await subscriber.handle(revision)
    orchestrator.post_projection_ack.assert_not_called()


@pytest.mark.asyncio
async def test_handle_posts_failed_ack_when_rewriter_raises():
    rewriter_mock = AsyncMock()
    rewriter_mock.apply.side_effect = RuntimeError("boom")
    orchestrator = AsyncMock()

    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter_mock,
        orchestrator_client=orchestrator,
    )
    revision = {
        "revision_id": "rev-fail",
        "ph_id": "ph-1",
        "previous_identity_id": "alice",
        "new_identity_id": "bob",
        "reason": "operator_correction",
        "evidence": {},
        "revision_time": "2026-06-20T12:00:00Z",
        "required_projections": ["cts_internal", "cc"],
    }
    result = await subscriber.handle(revision)
    assert result is False
    orchestrator.post_projection_ack.assert_called_once()
    assert orchestrator.post_projection_ack.call_args.kwargs["status"] == "failed"
