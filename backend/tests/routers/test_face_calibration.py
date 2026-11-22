"""Face calibration review routes: a strict biometric-admin grant, thin routes, real labeler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context, invalidate_lookup_cache
from backend.core.exceptions import register_exception_handlers
from backend.integrations.minio_client import MinioClient
from backend.integrations.person_id_client import PersonIDUpstreamError
from backend.routers.dependencies import (
    get_config_minio_client,
    get_face_calibration_service,
    get_identity_review_registry,
)
from backend.routers.face_calibration import router
from backend.schemas.face_calibration import (
    AttestationAuditSummaryEnvelope,
    AttestedFaceListResponse,
    CalibrationCandidateListResponse,
    CalibrationCandidateView,
    FaceCalibrationSummaryEnvelope,
    PromoteCalibrationCandidateResponse,
)
from backend.schemas.identity_review import BatchReviewResponse, ReviewItemResult
from backend.services.identity_review.registry import ReviewSubject

_VIEW = CalibrationCandidateView(
    candidate_id="c1",
    captured_at="2026-10-21T09:00:00+00:00",
    camera_id="cam-1",
    crop_url="https://minio/presigned",
    quality_score=0.4,
    quality_version="heuristic-v1",
    interocular_px=18.0,
    yaw_deg=0.0,
    pitch_deg=-5.0,
    nearest_person_id="amma",
    nearest_similarity=0.36,
    label_state="unlabeled",
)
_SUMMARY = FaceCalibrationSummaryEnvelope(
    by_state={"unlabeled": 3, "labeled": 0, "rejected": 0},
    by_label_kind={},
    by_quality_decile={},
    by_camera={},
    identities=[],
    not_enrolled_episodes=0,
    capture_enabled=False,
)


def _build(
    roles: list[str] | None = None,
    *,
    tokens: frozenset[str] = frozenset(),
    name: str = "caregiver-ops",
):
    svc = MagicMock()
    svc.list_candidates = AsyncMock(
        return_value=CalibrationCandidateListResponse(candidates=[_VIEW], next_cursor="k")
    )
    svc.label = AsyncMock(return_value=_VIEW)
    svc.reject = AsyncMock(return_value=_VIEW)
    svc.registry = MagicMock()
    svc.registry.decide = AsyncMock(
        return_value=BatchReviewResponse(
            results=[ReviewItemResult(id="c1", ok=True)], reviewed=1, failed=0, effect="Labeled."
        )
    )
    svc.delete = AsyncMock(return_value=None)
    svc.promote = AsyncMock(
        return_value=PromoteCalibrationCandidateResponse(
            candidate_id="c1",
            person_id="amma",
            pose_bin="down",
            embedding_id=42,
            gallery_revision=2,
            prototype_count=3,
            counts_by_bin={"frontal": 2, "down": 1},
        )
    )
    svc.get_summary = AsyncMock(return_value=_SUMMARY)
    attested = _VIEW.model_copy(
        update={"label_state": "attested", "attestation_grade": "room", "label_kind": "member"}
    )
    svc.list_attested = AsyncMock(return_value=AttestedFaceListResponse(candidates=[attested]))
    svc.attestation_audit_sample = AsyncMock(
        return_value=AttestedFaceListResponse(candidates=[attested])
    )
    svc.audit_attested_face = AsyncMock(
        return_value=attested.model_copy(update={"audit_verdict": "correct"})
    )
    svc.attestation_audit_summary = AsyncMock(
        return_value=AttestationAuditSummaryEnvelope(
            attested=4,
            audited=1,
            correct=1,
            wrong=0,
            not_a_face=0,
            precision_lower_bound=0.21,
            min_audited=200,
            min_precision_lower_bound=0.99,
            meets_bar=False,
        )
    )
    minio = MagicMock(spec=MinioClient)
    minio.generate_presigned_url.return_value = "https://minio/presigned"
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name=name, roles=list(roles or ()), tokens=tokens
    )
    app.dependency_overrides[get_face_calibration_service] = lambda: svc
    app.dependency_overrides[get_identity_review_registry] = lambda: svc.registry
    app.dependency_overrides[get_config_minio_client] = lambda: minio
    invalidate_lookup_cache()
    return TestClient(app), svc, minio


_ROUTES = [
    ("get", "/api/v1/face-calibration/candidates", None, 200),
    ("post", "/api/v1/face-calibration/candidates/c1/label", {"label_kind": "not_a_face"}, 200),
    ("post", "/api/v1/face-calibration/candidates/c1/reject", {}, 200),
    (
        "post",
        "/api/v1/face-calibration/candidates/review",
        {"candidate_ids": ["c1"], "verdict": "not_enrolled"},
        200,
    ),
    ("delete", "/api/v1/face-calibration/candidates/c1", None, 204),
    ("post", "/api/v1/face-calibration/candidates/c1/promote", None, 200),
    ("get", "/api/v1/face-calibration/summary", None, 200),
    ("get", "/api/v1/face-calibration/attestations", None, 200),
    ("get", "/api/v1/face-calibration/attestations/audit-sample", None, 200),
    ("post", "/api/v1/face-calibration/attestations/c1/audit", {"verdict": "correct"}, 200),
    ("get", "/api/v1/face-calibration/attestations/audit-summary", None, 200),
]


def _call(client: TestClient, method: str, path: str, body):
    return (
        getattr(client, method)(path, json=body)
        if body is not None
        else getattr(client, method)(path)
    )


@pytest.mark.parametrize(
    ("roles", "tokens"),
    [
        (["caregiver"], frozenset()),
        ([], frozenset({"visitors:review"})),
        ([], frozenset({"cts.identity.gallery:review"})),
    ],
)
def test_other_grants_cannot_reach_any_route(roles: list[str], tokens: frozenset[str]) -> None:
    client, _, _ = _build(roles, tokens=tokens)
    for method, path, body, _ok in _ROUTES:
        assert _call(client, method, path, body).status_code == 403, f"{method} {path} leaked"


@pytest.mark.parametrize(
    ("roles", "tokens"),
    [
        ([], frozenset({"face_calibration:review"})),
        (["caregiver_admin"], frozenset()),
        (["admin"], frozenset()),
    ],
)
def test_review_grant_reaches_every_route(roles: list[str], tokens: frozenset[str]) -> None:
    client, _, _ = _build(roles, tokens=tokens)
    for method, path, body, ok in _ROUTES:
        assert _call(client, method, path, body).status_code == ok, f"{method} {path} denied"


def test_list_defaults_to_unlabeled_and_presigns() -> None:
    client, svc, _ = _build(["admin"])
    body = client.get("/api/v1/face-calibration/candidates", params={"limit": 20}).json()
    assert body["candidates"][0]["crop_url"] == "https://minio/presigned"
    kwargs = svc.list_candidates.await_args.kwargs
    assert (kwargs["state"], kwargs["limit"], kwargs["cursor"]) == ("unlabeled", 20, None)
    assert kwargs["presign"]("calibration/x.png") == "https://minio/presigned"
    assert kwargs["presign"](None) is None


def test_label_records_the_authenticated_caller_not_the_browser() -> None:
    client, svc, _ = _build(["admin"], name="admin-tablet")
    resp = client.post(
        "/api/v1/face-calibration/candidates/c1/label",
        json={"label_kind": "member", "label_identity_id": "amma"},
    )
    assert resp.status_code == 200
    kwargs = svc.label.await_args.kwargs
    assert (kwargs["label_kind"], kwargs["label_identity_id"], kwargs["actor"]) == (
        "member",
        "amma",
        "admin-tablet",
    )


def test_batch_review_records_the_caller_and_refuses_member_labels() -> None:
    client, svc, _ = _build(["admin"], name="admin-tablet")
    ok = client.post(
        "/api/v1/face-calibration/candidates/review",
        json={"candidate_ids": ["c1", "c2"], "verdict": "not_usable"},
    )
    assert ok.status_code == 200
    args, kwargs = svc.registry.decide.await_args
    assert args == ("face_calibration", "not_usable", [ReviewSubject("c1"), ReviewSubject("c2")])
    assert kwargs["actor"] == "admin-tablet"

    member = client.post(
        "/api/v1/face-calibration/candidates/review",
        json={"candidate_ids": ["c1"], "verdict": "is_member", "target_identity_id": "amma"},
    )
    assert member.status_code == 422
    assert svc.registry.decide.await_count == 1


@pytest.mark.parametrize(
    "body",
    [
        {"label_kind": "member"},
        {"label_kind": "not_enrolled", "label_identity_id": "amma"},
        {"label_kind": "not_a_face", "labeled_by": "someone-else"},
        {"label_kind": "maybe"},
    ],
)
def test_invalid_label_bodies_are_rejected(body: dict) -> None:
    client, svc, _ = _build(["admin"])
    assert client.post("/api/v1/face-calibration/candidates/c1/label", json=body).status_code == 422
    svc.label.assert_not_awaited()


@pytest.mark.parametrize(("upstream", "expected"), [(404, 404), (422, 422), (503, 502), (500, 502)])
def test_upstream_errors_map_distinctly(upstream: int, expected: int) -> None:
    client, svc, _ = _build(["admin"])
    svc.reject.side_effect = PersonIDUpstreamError(upstream, "upstream said no")
    resp = client.post("/api/v1/face-calibration/candidates/c1/reject")
    assert resp.status_code == expected


def test_promote_passes_authenticated_actor_and_maps_conflict() -> None:
    client, svc, _ = _build(tokens=frozenset({"face_calibration:review"}), name="caregiver-admin")
    resp = client.post("/api/v1/face-calibration/candidates/c1/promote")
    assert resp.status_code == 200
    assert resp.json()["gallery_revision"] == 2
    assert svc.promote.await_args.kwargs == {"actor": "caregiver-admin"}

    svc.promote.side_effect = PersonIDUpstreamError(409, "already promoted")
    conflict = client.post("/api/v1/face-calibration/candidates/c1/promote")
    assert conflict.status_code == 409


def test_attested_faces_are_presigned_and_filtered() -> None:
    client, svc, _ = _build(["admin"])
    body = client.get(
        "/api/v1/face-calibration/attestations",
        params={"identity_id": "amma", "audited": "false", "limit": 30},
    ).json()
    assert body["candidates"][0]["label_state"] == "attested"
    assert body["candidates"][0]["attestation_grade"] == "room"
    kwargs = svc.list_attested.await_args.kwargs
    assert (kwargs["identity_id"], kwargs["audited"], kwargs["limit"]) == ("amma", False, 30)
    assert kwargs["presign"]("calibration/attested/x.png") == "https://minio/presigned"


def test_audit_records_the_authenticated_caller_not_the_browser() -> None:
    client, svc, _ = _build(["admin"], name="admin-tablet")
    resp = client.post("/api/v1/face-calibration/attestations/c1/audit", json={"verdict": "wrong"})
    assert resp.status_code == 200
    args, kwargs = svc.audit_attested_face.await_args
    assert args == ("c1",)
    assert (kwargs["verdict"], kwargs["actor"]) == ("wrong", "admin-tablet")
    spoofed = client.post(
        "/api/v1/face-calibration/attestations/c1/audit",
        json={"verdict": "correct", "audited_by": "someone-else"},
    )
    assert spoofed.status_code == 422
    unknown = client.post(
        "/api/v1/face-calibration/attestations/c1/audit", json={"verdict": "maybe"}
    )
    assert unknown.status_code == 422
    assert svc.audit_attested_face.await_count == 1


def test_audit_sample_size_is_bounded() -> None:
    client, svc, _ = _build(["admin"])
    assert (
        client.get(
            "/api/v1/face-calibration/attestations/audit-sample", params={"n": 500}
        ).status_code
        == 422
    )
    client.get("/api/v1/face-calibration/attestations/audit-sample", params={"n": 25})
    assert svc.attestation_audit_sample.await_args.kwargs["n"] == 25
