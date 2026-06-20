"""M00 characterization for keyframe card identity collapse."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.routers.cts_keyframes import router
from backend.routers.dependencies import get_orchestrator_client

_FIXTURE = Path(__file__).parents[1] / "fixtures/identity_integrity/keyframe_identity_collapse.json"


@pytest.mark.xfail(
    strict=True,
    reason="M07 removes this xfail when physical-frame cards aggregate all bbox identities",
)
def test_keyframe_card_exposes_every_bbox_identity() -> None:
    data = json.loads(_FIXTURE.read_text())
    orchestrator = MagicMock(spec=OrchestratorClient)
    orchestrator.list_keyframes = AsyncMock(return_value=[data["keyframe"]])
    app = FastAPI()
    app.state.minio_client = None
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="synthetic",
        name="characterization",
        permissions=["*"],
    )
    app.dependency_overrides[get_orchestrator_client] = lambda: orchestrator
    settings = Settings.from_dict({"cts": {"enabled": True}})

    with (
        patch("backend.routers.cts_deps.settings", settings),
        patch(
            "backend.routers.cts_keyframes._enrich_with_signals",
            side_effect=lambda keyframes, _person_ids: keyframes,
        ),
        TestClient(app) as client,
    ):
        response = client.get("/api/v1/cts/keyframes")

    assert response.status_code == 200
    summary = response.json()["keyframes"][0]["identity_summary"]
    assert {item["effective_identity_id"] for item in summary} == {
        "resident-alpha",
        "resident-beta",
    }
