"""M09: ReID review BFF service - media state-awareness, mapping, error semantics."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.upstream_errors import UpstreamError
from backend.services.cts.reid_review_service import (
    ReIDReviewService,
    ReviewContractError,
    ReviewUpstreamError,
)


def _raw_candidate(state: str = "pending_review") -> dict:
    return {
        "candidate_id": "c1",
        "identity_id": "amma",
        "effective_identity_id": "amma",
        "state": state,
        "candidate_reason": "multiview",
        "model_version": "v1",
        "preprocessing_version": "v1",
        "crop_key": "reid-candidates/v1/c1.jpg",
        "source_frame_key": "reid-candidates-frames/v1/c1.jpg",
        "orientation": 4,
        "quality": 0.8,
        "is_truncated": False,
        "is_occluded": False,
        "audit_version": 1,
    }


def _presign(key):
    return f"https://minio/{key}" if key else None


@pytest.fixture
def service_and_client():
    client = MagicMock()
    return ReIDReviewService(client), client


async def test_effective_identity_maps_to_person_id(service_and_client):
    service, client = service_and_client
    client.get_review_candidate = AsyncMock(
        return_value={
            "candidate": _raw_candidate(),
            "events": [],
            "eligibility": {"eligible": True, "model_compatible": True, "reasons": []},
        }
    )
    detail = await service.get_detail("c1", presign=_presign)
    assert detail.candidate.person_id == "amma"


async def test_pending_candidate_presigns_media(service_and_client):
    service, client = service_and_client
    client.get_review_candidate = AsyncMock(
        return_value={
            "candidate": _raw_candidate(),
            "events": [],
            "eligibility": {"eligible": True, "model_compatible": True, "reasons": []},
        }
    )
    detail = await service.get_detail("c1", presign=_presign)
    assert detail.candidate.crop_url == "https://minio/reid-candidates/v1/c1.jpg"
    assert detail.candidate.frame_url is not None
    # Object keys are never exposed to the browser.
    assert "crop_key" not in detail.candidate.model_dump()


async def test_rejected_candidate_never_presigns_crop(service_and_client):
    service, client = service_and_client
    client.reject_review_candidate = AsyncMock(return_value=_raw_candidate(state="rejected"))
    view = await service.reject(
        "c1",
        actor="alice",
        base_audit_version=1,
        reason="wrong_person",
        note=None,
        presign=_presign,
    )
    # The crop object is deleted upstream; presigning it would 404 in the browser.
    assert view.crop_url is None
    assert view.frame_url is None


async def test_actor_injected_into_upstream_payload(service_and_client):
    service, client = service_and_client
    client.approve_review_candidate = AsyncMock(
        return_value=_raw_candidate(state="operator_verified")
    )
    await service.approve("c1", actor="alice", base_audit_version=1, note="ok")
    payload = client.approve_review_candidate.await_args.kwargs["payload"]
    assert payload["actor"] == "alice"


async def test_stale_upstream_status_preserved(service_and_client):
    service, client = service_and_client
    body = json.dumps({"detail": {"code": "reid_review.stale", "message": "moved"}})
    client.approve_review_candidate = AsyncMock(
        side_effect=UpstreamError("tracking_orchestrator", 409, body)
    )
    with pytest.raises(ReviewUpstreamError) as ei:
        await service.approve("c1", actor="alice", base_audit_version=1, note=None)
    assert ei.value.status == 409
    assert ei.value.code == "reid_review.stale"


async def test_server_error_becomes_502(service_and_client):
    service, client = service_and_client
    client.get_review_counts = AsyncMock(
        side_effect=UpstreamError("tracking_orchestrator", 500, "boom")
    )
    with pytest.raises(ReviewUpstreamError) as ei:
        await service.counts()
    assert ei.value.status == 502


async def test_malformed_envelope_is_contract_error(service_and_client):
    service, client = service_and_client
    client.list_review_candidates = AsyncMock(return_value={"unexpected": True})
    with pytest.raises(ReviewContractError):
        await service.list_candidates(params={})
