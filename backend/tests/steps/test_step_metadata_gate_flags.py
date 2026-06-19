"""Tests for step metadata gate flags (gate_safe, gate_only)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.routers.pipeline import router
from backend.steps import StepRegistry


@pytest.mark.parametrize(
    ("step_type", "expected_gate_safe"),
    [
        ("media_window_poll", True),
        ("scene_analysis", True),
        ("image_crop", True),
        ("person_identification", True),
        ("presence_query", True),
        ("semantic_memory_query", True),
        ("llm_call", True),
        ("condition", True),
        ("gate_verdict", True),
        ("notification", False),
        ("ha_action", False),
        ("home_state", False),
        ("semantic_memory_write", False),
        ("wait", False),
        ("interactive_prompt", False),
        ("quiz_start", False),
        ("guided_task_start", False),
    ],
)
def test_expected_steps_are_gate_safe(step_type: str, expected_gate_safe: bool):
    StepRegistry.discover()
    handler = StepRegistry.get(step_type)
    assert handler is not None, f"Step type {step_type} is not registered"
    meta = handler.metadata()
    assert meta.gate_safe == expected_gate_safe, f"Step type {step_type} gate_safe flag was expected to be {expected_gate_safe}"


def test_gate_verdict_is_gate_only_and_hidden_from_normal_palette():
    StepRegistry.discover()
    handler = StepRegistry.get("gate_verdict")
    assert handler is not None
    meta = handler.metadata()
    assert meta.gate_only is True
    # Verify that normal palette (where gate_only steps are excluded) would not include it
    normal_steps = [m for m in StepRegistry.all_metadata() if not m.gate_only]
    assert all(m.type_name != "gate_verdict" for m in normal_steps)


def test_metadata_endpoint_exposes_gate_safe_and_gate_only():
    app = FastAPI()

    # Override auth with admin context
    async def override_auth():
        return AuthContext(
            key="test", name="Test Admin", permissions=["*"], device_type=None, sensor_id=None
        )

    app.dependency_overrides[get_auth_context] = override_auth
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)

    resp = client.get("/api/v1/pipeline/step-types")
    assert resp.status_code == 200
    data = resp.json()

    # Verify gate_safe and gate_only are present in the response
    gate_verdict_meta = next(item for item in data if item["type_name"] == "gate_verdict")
    assert gate_verdict_meta["gate_safe"] is True
    assert gate_verdict_meta["gate_only"] is True

    condition_meta = next(item for item in data if item["type_name"] == "condition")
    assert condition_meta["gate_safe"] is True
    assert condition_meta["gate_only"] is False
