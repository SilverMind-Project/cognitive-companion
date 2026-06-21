"""MCP/BFF parity for grouped keyframes (D6 guarantee).

The MCP tool ``list_keyframe_frames`` and the router ``GET /cts/keyframes``
must call the same ``KeyframeReadService.list_frames`` and return the same
physical-frame cards.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.exceptions import register_exception_handlers
from backend.mcp.server import _svc
from backend.mcp.server import list_keyframe_frames as mcp_list_keyframe_frames
from backend.routers.cts_keyframes import router as keyframes_router
from backend.routers.dependencies import get_keyframe_read_service
from backend.schemas.cts_keyframe import (
    IdentitySummaryItem,
    KeyframePage,
    PhysicalFrameCard,
)


def _page() -> KeyframePage:
    card = PhysicalFrameCard(
        physical_frame_id="pf-1",
        camera_id="cam-a",
        minio_key="frames/cam-a/0001-0.jpg",
        captured_at="2026-06-19T12:00:00+00:00",
        frame_width=1920,
        frame_height=1080,
        triggers=[],
        trigger_reasons=["periodic"],
        identity_summary=[
            IdentitySummaryItem(
                effective_identity_id="amma",
                person_id="amma",
                count=2,
                source_badges=["ArcFace"],
            )
        ],
        unknown_count=0,
        conflict_count=0,
        pending_review_count=0,
        bboxes=[],
        keyframe_id="pf-1",
        sample_id="pf-1",
    )
    return KeyframePage(keyframes=[card], count=1, total=1)


@pytest.fixture(autouse=True)
def reset_svc():
    original = _svc.__dict__.copy()
    yield
    for k, v in original.items():
        setattr(_svc, k, v)


async def test_mcp_and_bff_share_service_and_envelope() -> None:
    svc_mock = MagicMock()
    svc_mock.list_frames = AsyncMock(return_value=_page())

    # MCP path.
    _svc.keyframe_read_service = svc_mock
    mcp_result = await mcp_list_keyframe_frames(person_id="amma")

    # BFF path.
    app = FastAPI()
    app.state.minio_client = None
    register_exception_handlers(app)
    app.include_router(keyframes_router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.dependency_overrides[get_keyframe_read_service] = lambda: svc_mock
    cfg = Settings.from_dict({"cts": {"enabled": True}})
    with patch("backend.routers.cts_deps.settings", cfg):
        resp = TestClient(app).get("/api/v1/cts/keyframes", params={"person_id": "amma"})

    assert resp.status_code == 200, resp.text
    bff_result = resp.json()

    # Same service method on both paths, with the effective-identity filter.
    assert svc_mock.list_frames.await_count == 2
    for call in svc_mock.list_frames.await_args_list:
        assert call.kwargs["effective_identity_id"] == "amma"

    mcp_card = mcp_result["keyframes"][0]
    bff_card = bff_result["keyframes"][0]
    assert mcp_card["physical_frame_id"] == bff_card["physical_frame_id"]
    assert (
        mcp_card["identity_summary"][0]["effective_identity_id"]
        == bff_card["identity_summary"][0]["effective_identity_id"]
        == "amma"
    )
