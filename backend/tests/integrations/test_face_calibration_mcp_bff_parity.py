"""Face calibration summary: the BFF route and the MCP tool read the same service method.

Labeling, rejecting, and deleting captures stay off MCP: they change the biometric calibration
set and are an operator action, like visitor naming.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context, invalidate_lookup_cache
from backend.core.exceptions import register_exception_handlers
from backend.integrations.person_id_client import PersonIDUpstreamError
from backend.mcp.server import _svc, _tool_handlers
from backend.mcp.server import get_face_calibration_summary as mcp_summary
from backend.routers.dependencies import get_face_calibration_service
from backend.routers.face_calibration import router
from backend.schemas.face_calibration import (
    CalibrationIdentityProgressView,
    FaceCalibrationSummaryEnvelope,
)

_ENVELOPE = FaceCalibrationSummaryEnvelope(
    by_state={"unlabeled": 12, "labeled": 30, "rejected": 2},
    by_label_kind={"member": 25, "not_enrolled": 5},
    by_quality_decile={"2": 10, "6": 20},
    by_camera={"cam-1": 30},
    identities=[
        CalibrationIdentityProgressView(
            identity_id="amma", labeled_faces=25, episodes=4, target_labeled_faces=150
        )
    ],
    not_enrolled_episodes=2,
    capture_enabled=True,
)


@pytest.fixture(autouse=True)
def _restore_mcp_services():
    original = _svc.__dict__.copy()
    yield
    for key, value in original.items():
        setattr(_svc, key, value)


def _service(result: FaceCalibrationSummaryEnvelope | Exception) -> MagicMock:
    svc = MagicMock()
    if isinstance(result, Exception):
        svc.get_summary = AsyncMock(side_effect=result)
    else:
        svc.get_summary = AsyncMock(return_value=result)
    return svc


async def test_route_and_mcp_tool_return_the_same_envelope() -> None:
    svc = _service(_ENVELOPE)
    _svc.face_calibration_service = svc
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="admin", permissions=["face_calibration.review"]
    )
    app.dependency_overrides[get_face_calibration_service] = lambda: svc
    invalidate_lookup_cache()

    route_body = TestClient(app).get("/api/v1/face-calibration/summary").json()
    mcp_body = await mcp_summary()

    assert route_body == mcp_body == _ENVELOPE.model_dump(mode="json")
    assert svc.get_summary.await_count == 2


async def test_mcp_tool_reports_upstream_failure_and_missing_service() -> None:
    _svc.face_calibration_service = _service(PersonIDUpstreamError(502, "unreachable"))
    assert await mcp_summary() == {"error": "unreachable"}
    _svc.face_calibration_service = None
    assert await mcp_summary() == {"error": "face_calibration_service unavailable"}


def test_calibration_mutations_are_not_mcp_tools() -> None:
    calibration_tools = {name for name in _tool_handlers if "calibration" in name}
    assert calibration_tools == {"get_face_calibration_summary"}
