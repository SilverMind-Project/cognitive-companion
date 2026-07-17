"""Admin health probes pass the upstream body through (M17b).

The probes return ``{"configured": True, **upstream_health_body}``, and the admin dashboard
reads service-specific keys straight off the result -- `DashboardView.vue:239-240` renders the
TTS tile from `default_engine`, `gpu_available` and `gpu_name`, none of which this codebase
declares.

Declaring `response_model=ServiceHealthOut` on these routes therefore only works because the
model sets `extra="allow"`. Without it Pydantic drops every undeclared key, the endpoint keeps
returning 200, and the tiles quietly degrade to "unknown - CPU". Nothing else would fail.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.schemas.admin import ServiceHealthOut


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/healthy", response_model=ServiceHealthOut)
    async def healthy() -> dict:
        # Byte-for-byte what tts_health returns on its healthy branch.
        return {
            "configured": True,
            "status": "ok",
            "default_engine": "piper",
            "gpu_available": True,
            "gpu_name": "RTX 4090",
        }

    @app.get("/not-configured", response_model=ServiceHealthOut)
    async def not_configured() -> dict:
        return {"configured": False, "status": "not_configured"}

    @app.get("/no-status", response_model=ServiceHealthOut)
    async def no_status() -> dict:
        # A healthy upstream need not report a status field.
        return {"configured": True, "uptime_seconds": 12}

    return TestClient(app)


def test_upstream_keys_survive_the_response_model() -> None:
    body = _client().get("/healthy").json()

    for key in ("default_engine", "gpu_available", "gpu_name"):
        assert key in body, (
            f"{key} was dropped by ServiceHealthOut. The admin dashboard reads it off the TTS "
            "health payload; extra='allow' must stay on the model."
        )
    assert body["gpu_name"] == "RTX 4090"


def test_declared_fields_still_serialize() -> None:
    body = _client().get("/healthy").json()

    assert body["configured"] is True
    assert body["status"] == "ok"


def test_not_configured_branch_validates() -> None:
    assert _client().get("/not-configured").json() == {
        "configured": False,
        "status": "not_configured",
    }


def test_status_is_optional() -> None:
    body = _client().get("/no-status").json()

    assert body["configured"] is True
    assert body["status"] is None
    assert body["uptime_seconds"] == 12
