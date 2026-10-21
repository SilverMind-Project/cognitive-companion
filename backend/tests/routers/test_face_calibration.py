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
from backend.routers.dependencies import get_config_minio_client, get_face_calibration_service
from backend.routers.face_calibration import router
from backend.schemas.face_calibration import (
    CalibrationCandidateListResponse,
    CalibrationCandidateView,
    FaceCalibrationSummaryEnvelope,
)

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


def _build(permissions: list[str], *, name: str = "caregiver-ops"):
    svc = MagicMock()
    svc.list_candidates = AsyncMock(
        return_value=CalibrationCandidateListResponse(candidates=[_VIEW], next_cursor="k")
    )
    svc.label = AsyncMock(return_value=_VIEW)
    svc.reject = AsyncMock(return_value=_VIEW)
    svc.delete = AsyncMock(return_value=None)
    svc.get_summary = AsyncMock(return_value=_SUMMARY)
    minio = MagicMock(spec=MinioClient)
    minio.generate_presigned_url.return_value = "https://minio/presigned"
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name=name, permissions=permissions
    )
    app.dependency_overrides[get_face_calibration_service] = lambda: svc
    app.dependency_overrides[get_config_minio_client] = lambda: minio
    invalidate_lookup_cache()
    return TestClient(app), svc, minio


_ROUTES = [
    ("get", "/api/v1/face-calibration/candidates", None, 200),
    ("post", "/api/v1/face-calibration/candidates/c1/label", {"label_kind": "not_a_face"}, 200),
    ("post", "/api/v1/face-calibration/candidates/c1/reject", {}, 200),
    ("delete", "/api/v1/face-calibration/candidates/c1", None, 204),
    ("get", "/api/v1/face-calibration/summary", None, 200),
]


def _call(client: TestClient, method: str, path: str, body):
    return (
        getattr(client, method)(path, json=body)
        if body is not None
        else getattr(client, method)(path)
    )


@pytest.mark.parametrize(
    "perms", [["caregiver"], ["visitors.review"], ["cts.identity.gallery_review"]]
)
def test_other_grants_cannot_reach_any_route(perms: list[str]) -> None:
    client, _, _ = _build(perms)
    for method, path, body, _ok in _ROUTES:
        assert _call(client, method, path, body).status_code == 403, f"{method} {path} leaked"


@pytest.mark.parametrize("perms", [["face_calibration.review"], ["caregiver_admin"], ["*"]])
def test_review_grant_reaches_every_route(perms: list[str]) -> None:
    client, _, _ = _build(perms)
    for method, path, body, ok in _ROUTES:
        assert _call(client, method, path, body).status_code == ok, f"{method} {path} denied"


def test_list_defaults_to_unlabeled_and_presigns() -> None:
    client, svc, _ = _build(["*"])
    body = client.get("/api/v1/face-calibration/candidates", params={"limit": 20}).json()
    assert body["candidates"][0]["crop_url"] == "https://minio/presigned"
    kwargs = svc.list_candidates.await_args.kwargs
    assert (kwargs["state"], kwargs["limit"], kwargs["cursor"]) == ("unlabeled", 20, None)
    assert kwargs["presign"]("calibration/x.png") == "https://minio/presigned"
    assert kwargs["presign"](None) is None


def test_label_records_the_authenticated_caller_not_the_browser() -> None:
    client, svc, _ = _build(["*"], name="admin-tablet")
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
    client, svc, _ = _build(["*"])
    assert client.post("/api/v1/face-calibration/candidates/c1/label", json=body).status_code == 422
    svc.label.assert_not_awaited()


@pytest.mark.parametrize(("upstream", "expected"), [(404, 404), (422, 422), (503, 502), (500, 502)])
def test_upstream_errors_map_distinctly(upstream: int, expected: int) -> None:
    client, svc, _ = _build(["*"])
    svc.reject.side_effect = PersonIDUpstreamError(upstream, "upstream said no")
    resp = client.post("/api/v1/face-calibration/candidates/c1/reject")
    assert resp.status_code == expected
