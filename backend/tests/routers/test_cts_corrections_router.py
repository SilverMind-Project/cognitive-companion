"""M08: cts_ph correction endpoints — auth, actor injection, error mapping, parity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.exceptions import register_exception_handlers
from backend.routers.cts_ph import router
from backend.routers.dependencies import get_identity_correction_service
from backend.schemas.cts_correction import (
    CorrectionJobResponse,
    CorrectionResultResponse,
    SegmentBoundaryView,
    SegmentProposalResponse,
)
from backend.services.cts.identity_correction_service import CorrectionUpstreamError


def _proposal() -> SegmentProposalResponse:
    return SegmentProposalResponse(
        ph_id="ph-1",
        observation_ids=["o1", "o2"],
        start=SegmentBoundaryView(observation_id="o1", captured_at="2026-06-20T12:00:00+00:00", reason="segment_edge"),
        end=SegmentBoundaryView(observation_id="o2", captured_at="2026-06-20T12:00:05+00:00", reason="segment_edge"),
        ph_version=2,
        effective_identity_id="amma",
        person_id="amma",
    )


def _result() -> CorrectionResultResponse:
    return CorrectionResultResponse(
        revision_id="rev-1",
        correction_id="corr-1",
        ph_id="ph-1",
        previous_identity_id="amma",
        new_identity_id="grandma",
        range_id="range-1",
        new_ph_id=None,
        job_status="applying",
    )


def _build_app(permissions: list[str]):
    cfg = Settings.from_dict({"cts": {"enabled": True}})
    svc = MagicMock()
    svc.propose_segment = AsyncMock(return_value=_proposal())
    svc.apply_correction = AsyncMock(return_value=_result())
    svc.compensate = AsyncMock(return_value=_result())
    svc.get_job = AsyncMock(
        return_value=CorrectionJobResponse(
            revision_id="rev-1",
            job_id="job-1",
            status="completed",
            required_projections=["cc"],
            row_counts={"cc": 2},
            attempts=1,
            last_error=None,
        )
    )

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="caregiver@home", permissions=permissions
    )
    app.dependency_overrides[get_identity_correction_service] = lambda: svc
    patcher = patch("backend.routers.cts_deps.settings", cfg)
    patcher.start()
    return TestClient(app), svc, patcher


# Permissions resolve to endpoint patterns (the keystore matches METHOD /path).
# caregiver_admin/operator grant "POST /api/v1/cts/identity/*" in auth.yaml, which
# covers propose/apply/compensate; "GET /api/v1/*" covers the job read.
_FULL = ["*"]
# A principal allowed to propose (and read jobs) but NOT to apply/compensate.
_VIEW_ONLY = ["GET /api/v1/*", "POST /api/v1/cts/identity/corrections/propose"]


@pytest.fixture
def client_full():
    c, svc, p = _build_app(_FULL)
    yield c, svc
    p.stop()


@pytest.fixture
def client_view_only():
    c, svc, p = _build_app(_VIEW_ONLY)
    yield c, svc
    p.stop()


def test_propose_returns_proposal(client_full):
    client, _svc = client_full
    r = client.post("/api/v1/cts/identity/corrections/propose", json={"ph_id": "ph-1"})
    assert r.status_code == 200
    assert r.json()["ph_version"] == 2


def test_apply_injects_actor_from_auth(client_full):
    client, svc = client_full
    r = client.post(
        "/api/v1/cts/identity/corrections/apply",
        json={
            "ph_id": "ph-1",
            "reason_code": "wrong_person",
            "observation_start": "2026-06-20T12:00:00+00:00",
            "observation_end": "2026-06-20T12:00:05+00:00",
            "base_ph_version": 2,
            "target_identity_id": "grandma",
        },
    )
    assert r.status_code == 200
    # The router supplies a server-side actor (from request.state.auth_context via
    # _actor); the browser payload never carries it. The actor-override semantics
    # are unit-tested in test_identity_correction_service.
    kwargs = svc.apply_correction.call_args.kwargs
    assert "actor" in kwargs
    assert "actor" not in kwargs["payload"]


def test_apply_rejects_browser_actor_field(client_full):
    client, _svc = client_full
    # actor is extra="forbid" on the request schema.
    r = client.post(
        "/api/v1/cts/identity/corrections/apply",
        json={
            "ph_id": "ph-1",
            "reason_code": "wrong_person",
            "observation_start": "2026-06-20T12:00:00+00:00",
            "observation_end": "2026-06-20T12:00:05+00:00",
            "base_ph_version": 2,
            "actor": "attacker",
        },
    )
    assert r.status_code == 422


def test_apply_requires_correct_permission(client_view_only):
    client, _svc = client_view_only
    r = client.post(
        "/api/v1/cts/identity/corrections/apply",
        json={
            "ph_id": "ph-1",
            "reason_code": "wrong_person",
            "observation_start": "2026-06-20T12:00:00+00:00",
            "observation_end": "2026-06-20T12:00:05+00:00",
            "base_ph_version": 2,
            "target_identity_id": "grandma",
        },
    )
    assert r.status_code == 403


def test_stale_version_returns_409(client_full):
    client, svc = client_full
    svc.apply_correction = AsyncMock(
        side_effect=CorrectionUpstreamError(409, "correction.stale_version", "stale")
    )
    r = client.post(
        "/api/v1/cts/identity/corrections/apply",
        json={
            "ph_id": "ph-1",
            "reason_code": "wrong_person",
            "observation_start": "2026-06-20T12:00:00+00:00",
            "observation_end": "2026-06-20T12:00:05+00:00",
            "base_ph_version": 1,
            "target_identity_id": "grandma",
        },
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "correction.stale_version"


def test_job_status(client_full):
    client, _svc = client_full
    r = client.get("/api/v1/cts/identity/corrections/jobs/rev-1")
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


async def test_mcp_parity_reads_same_service():
    """Router and MCP tool read the same service function (D6)."""
    from backend.mcp import server as mcp_server

    svc = MagicMock()
    svc.propose_segment = AsyncMock(return_value=_proposal())
    svc.get_job = AsyncMock(
        return_value=CorrectionJobResponse(
            revision_id="rev-1",
            job_id="job-1",
            status="completed",
            required_projections=["cc"],
            row_counts={"cc": 2},
            attempts=1,
            last_error=None,
        )
    )
    mcp_server._svc.identity_correction_service = svc
    try:
        proposal = await mcp_server.propose_identity_correction("ph-1")
        job = await mcp_server.get_identity_correction_job("rev-1")
    finally:
        mcp_server._svc.identity_correction_service = None

    assert proposal["ph_version"] == 2
    assert job["status"] == "completed"
    svc.propose_segment.assert_awaited_once()
    svc.get_job.assert_awaited_once()
