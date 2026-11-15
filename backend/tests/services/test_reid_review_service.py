"""ReID review BFF service - media state-awareness, mapping, error semantics."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.exceptions import ValidationError as AppValidationError
from backend.core.upstream_errors import UpstreamError
from backend.services.cts.reid_review_service import (
    ReIDReviewAdapter,
    ReIDReviewService,
    ReviewContractError,
    ReviewUpstreamError,
)
from backend.services.identity_review.registry import ReviewDecision, ReviewSubject


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


async def test_reject_many_sends_one_reason_and_versions_and_maps_results(service_and_client):
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
    subjects = [ReviewSubject(c, i) for i, c in enumerate(["c1", "c2", "c3", "c4"])]

    results = await service.reject_many(
        subjects, actor="Caregiver Admin", reason="wrong_person", note=None
    )

    payload = client.reject_review_batch.await_args.kwargs["payload"]
    assert payload["actor"] == "Caregiver Admin"
    assert {i["reason"] for i in payload["items"]} == {"wrong_person"}
    assert [i["base_audit_version"] for i in payload["items"]] == [0, 1, 2, 3]
    assert [(r.id, r.ok, r.error_code) for r in results] == [
        ("c1", True, None),
        ("c2", False, "conflict"),
        ("c3", False, "not_found"),
        ("c4", False, "upstream_error"),
    ]


async def test_reject_many_malformed_envelope_is_contract_error(service_and_client):
    service, client = service_and_client
    client.reject_review_batch = AsyncMock(return_value={"results": [{"ok": True}]})

    with pytest.raises(ReviewContractError):
        await service.reject_many([ReviewSubject("c1", 1)], actor="a", reason="bad_bbox", note=None)


@pytest.mark.parametrize(
    ("verdict", "reason", "sent"),
    [("not_enrolled", None, "wrong_person"), ("not_usable", "low_quality", "low_quality")],
)
async def test_adapter_maps_each_rejection_verdict_to_its_reason(verdict, reason, sent):
    service = MagicMock()
    service.reject_many = AsyncMock(return_value=[])
    decision = ReviewDecision(
        surface="reid_review",
        verdict=verdict,
        subjects=(ReviewSubject("c1", 4),),
        reason=reason,
        note="n",
    )

    await ReIDReviewAdapter(service).apply(decision, actor="a")

    service.reject_many.assert_awaited_once_with(
        decision.subjects, actor="a", reason=sent, note="n"
    )


@pytest.mark.parametrize(
    "decision",
    [
        ReviewDecision(
            surface="reid_review", verdict="is_member", subjects=(ReviewSubject("c1", 1),)
        ),
        ReviewDecision(
            surface="reid_review", verdict="not_usable", subjects=(ReviewSubject("c1", 1),)
        ),
        ReviewDecision(
            surface="reid_review",
            verdict="not_usable",
            subjects=(ReviewSubject("c1", 1),),
            reason="wrong_person",
        ),
        ReviewDecision(
            surface="reid_review", verdict="not_enrolled", subjects=(ReviewSubject("c1"),)
        ),
    ],
)
async def test_adapter_refuses_approval_bad_reasons_and_missing_versions(decision):
    service = MagicMock()
    service.reject_many = AsyncMock()

    with pytest.raises(AppValidationError):
        await ReIDReviewAdapter(service).apply(decision, actor="a")
    service.reject_many.assert_not_called()
