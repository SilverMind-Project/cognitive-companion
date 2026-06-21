"""M00 characterization, flipped at M07.

Before M07 a keyframe card showed only the triggering PH's single identity.
After M07 the grouped physical-frame card aggregates every unique effective
bbox identity. The xfail is removed; this is now a passing invariant test.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.routers.cts_keyframes import router
from backend.routers.dependencies import get_keyframe_read_service
from backend.services.cts.keyframe_read_service import KeyframeReadService

_FIXTURE = Path(__file__).parents[1] / "fixtures/identity_integrity/keyframe_identity_collapse.json"


def test_keyframe_card_exposes_every_bbox_identity() -> None:
    data = json.loads(_FIXTURE.read_text())
    client_stub = MagicMock()
    client_stub.list_keyframe_frames = AsyncMock(return_value=data["page"])
    service = KeyframeReadService(client_stub)

    app = FastAPI()
    app.state.minio_client = None
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="synthetic",
        name="characterization",
        permissions=["*"],
    )
    app.dependency_overrides[get_keyframe_read_service] = lambda: service
    settings = Settings.from_dict({"cts": {"enabled": True}})

    with (
        patch("backend.routers.cts_deps.settings", settings),
        TestClient(app) as client,
    ):
        response = client.get("/api/v1/cts/keyframes")

    assert response.status_code == 200
    card = response.json()["keyframes"][0]
    summary = card["identity_summary"]
    assert {item["effective_identity_id"] for item in summary} == {
        "resident-alpha",
        "resident-beta",
    }
    # Effective identity maps to CC's internal person_id at the BFF boundary.
    assert {item["person_id"] for item in summary} == {"resident-alpha", "resident-beta"}
