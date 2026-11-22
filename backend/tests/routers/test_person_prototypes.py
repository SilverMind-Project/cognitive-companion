"""Person face prototype routes: strict token grants, crop presigning, and upstream mapping."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context, invalidate_lookup_cache
from backend.core.exceptions import register_exception_handlers
from backend.integrations.minio_client import MinioClient
from backend.integrations.person_id_client import (
    MemberPrototypesInfo,
    PersonIDUpstreamError,
    PrototypeInfo,
    RebuildPrototypesResult,
)
from backend.routers.dependencies import (
    get_config_minio_client,
    get_face_calibration_service,
)
from backend.routers.persons import router
from backend.services.face_calibration import FaceCalibrationReviewService

_AT = datetime(2026, 11, 19, 8, 0, tzinfo=UTC)


def _build(permissions: list[str], *, name: str = "ops"):
    pid = MagicMock()
    pid.list_member_prototypes = AsyncMock(
        return_value=MemberPrototypesInfo(
            person_id="amma",
            gallery_revision=3,
            prototypes=[
                PrototypeInfo(
                    prototype_id="p1",
                    person_id="amma",
                    pose_bin="down",
                    member_count=1,
                    source="promoted_capture",
                    quality_score=0.72,
                    quality_version="heuristic-v1",
                    crop_object_key="calibration/2026-11-19/c1.png",
                    approved_by="caregiver-admin",
                    approved_at=_AT,
                    created_at=_AT,
                )
            ],
            counts_by_bin={"down": 1},
        )
    )
    pid.rebuild_member_prototypes = AsyncMock(
        return_value=RebuildPrototypesResult(
            person_id="amma", prototype_count=2, counts_by_bin={"frontal": 1, "down": 1}
        )
    )
    pid.delete_member_prototype = AsyncMock(return_value=None)

    svc = FaceCalibrationReviewService(pid)
    minio = MagicMock(spec=MinioClient)
    minio.generate_presigned_url.return_value = "https://minio/presigned-proto"

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="k", name=name, roles=permissions
    )
    app.dependency_overrides[get_face_calibration_service] = lambda: svc
    app.dependency_overrides[get_config_minio_client] = lambda: minio
    invalidate_lookup_cache()
    return TestClient(app), pid, minio


def test_mcp_readonly_cannot_access_prototype_routes() -> None:
    client, _, _ = _build(["mcp_readonly"])
    assert client.get("/api/v1/persons/amma/prototypes").status_code == 403
    assert client.post("/api/v1/persons/amma/prototypes/rebuild").status_code == 403
    assert client.delete("/api/v1/persons/amma/prototypes/p1").status_code == 403


def test_caregiver_can_read_prototypes_but_cannot_mutate() -> None:
    client, _, _ = _build(["caregiver"])
    get_resp = client.get("/api/v1/persons/amma/prototypes")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["gallery_revision"] == 3
    assert body["prototypes"][0]["crop_url"] == "https://minio/presigned-proto"
    assert "crop_object_key" not in body["prototypes"][0]

    assert client.post("/api/v1/persons/amma/prototypes/rebuild").status_code == 403
    assert client.delete("/api/v1/persons/amma/prototypes/p1").status_code == 403


@pytest.mark.parametrize("perms", [["caregiver_admin"], ["admin"]])
def test_caregiver_admin_and_admin_can_read_rebuild_and_delete(perms: list[str]) -> None:
    client, pid, _ = _build(perms)
    assert client.get("/api/v1/persons/amma/prototypes").status_code == 200
    rebuilt = client.post("/api/v1/persons/amma/prototypes/rebuild")
    assert rebuilt.status_code == 200
    assert rebuilt.json()["prototype_count"] == 2
    deleted = client.delete("/api/v1/persons/amma/prototypes/p1")
    assert deleted.status_code == 204
    pid.delete_member_prototype.assert_awaited_once_with("amma", "p1")


@pytest.mark.parametrize(("upstream", "expected"), [(404, 404), (409, 409), (503, 502)])
def test_prototype_delete_maps_upstream_status(upstream: int, expected: int) -> None:
    client, pid, _ = _build(["caregiver_admin"])
    pid.delete_member_prototype.side_effect = PersonIDUpstreamError(upstream, "nope")
    resp = client.delete("/api/v1/persons/amma/prototypes/p1")
    assert resp.status_code == expected
