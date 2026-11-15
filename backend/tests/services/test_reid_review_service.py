"""ReID review BFF service - media state-awareness, mapping, error semantics."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.upstream_errors import UpstreamError
from backend.schemas.cts_reid_review import ReIDReviewBatchItem, ReIDReviewBatchRequest
from backend.services.cts.reid_review_service import (
    ReIDReviewService,
    ReviewContractError,
    ReviewUpstreamError,
)
from backend.services.identity_review.vocabulary import effect_text


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


async def test_demote_proxying(service_and_client):
    """M02: demote forwards the server-injected actor and base_audit_version,
    and the auto_verified -> pending_review transition round-trips."""
    service, client = service_and_client
    client.demote_review_candidate = AsyncMock(return_value=_raw_candidate(state="pending_review"))
    view = await service.demote("c1", actor="alice", base_audit_version=1, note="not trusted")
    payload = client.demote_review_candidate.await_args.kwargs["payload"]
    assert payload["actor"] == "alice"
    assert payload["base_audit_version"] == 1
    assert view.state == "pending_review"


async def test_auto_verified_state_round_trips(service_and_client):
    """M02: the fourth state is a valid envelope value, not a contract violation."""
    service, client = service_and_client
    client.get_review_candidate = AsyncMock(
        return_value={
            "candidate": _raw_candidate(state="auto_verified"),
            "events": [],
            "eligibility": {"eligible": True, "model_compatible": True, "reasons": []},
        }
    )
    detail = await service.get_detail("c1", presign=_presign)
    assert detail.candidate.state == "auto_verified"


async def test_out_of_vocabulary_state_from_upstream_is_contract_error(service_and_client):
    """A stale/newer upstream sending an unrecognized state is a typed 502,
    never silently accepted or coerced."""
    service, client = service_and_client
    client.get_review_candidate = AsyncMock(
        return_value={
            "candidate": _raw_candidate(state="bogus_state"),
            "events": [],
            "eligibility": {"eligible": True, "model_compatible": True, "reasons": []},
        }
    )
    with pytest.raises(ReviewContractError):
        await service.get_detail("c1", presign=_presign)


async def test_batch_review_rejects_each_with_one_reason_and_maps_results(service_and_client):
    service, client = service_and_client
    client.reject_review_batch = AsyncMock(
        return_value={
            "results": [
                {"candidate_id": "c1", "ok": True},
                {"candidate_id": "c2", "ok": False, "error_code": "conflict"},
                {"candidate_id": "c3", "ok": False, "error_code": "not_found"},
                {"candidate_id": "c4", "ok": False, "error_code": "surprise"},
            ],
            "rejected": 1,
            "failed": 3,
        }
    )
    request = ReIDReviewBatchRequest(
        verdict="not_enrolled",
        items=[
            ReIDReviewBatchItem(candidate_id=c, base_audit_version=i)
            for i, c in enumerate(["c1", "c2", "c3", "c4"])
        ],
    )

    result = await service.review_batch(request, actor="Caregiver Admin")

    payload = client.reject_review_batch.await_args.kwargs["payload"]
    assert payload["actor"] == "Caregiver Admin"
    assert {i["reason"] for i in payload["items"]} == {"wrong_person"}
    assert [i["base_audit_version"] for i in payload["items"]] == [0, 1, 2, 3]
    assert [(r.id, r.ok, r.error_code) for r in result.results] == [
        ("c1", True, None),
        ("c2", False, "conflict"),
        ("c3", False, "not_found"),
        ("c4", False, "upstream_error"),
    ]
    assert (result.reviewed, result.failed) == (1, 3)
    assert result.effect == effect_text("reid_review", "not_enrolled")


async def test_batch_review_malformed_envelope_is_contract_error(service_and_client):
    service, client = service_and_client
    client.reject_review_batch = AsyncMock(return_value={"results": [{"ok": True}]})
    request = ReIDReviewBatchRequest(
        verdict="not_usable",
        reason="bad_bbox",
        items=[ReIDReviewBatchItem(candidate_id="c1", base_audit_version=1)],
    )

    with pytest.raises(ReviewContractError):
        await service.review_batch(request, actor="a")
