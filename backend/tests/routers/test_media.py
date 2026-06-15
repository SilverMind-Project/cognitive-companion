"""Router tests for media observability endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.routers.media import router
from backend.schemas.media_observability import (
    AggregatorStateListEnvelope,
    CameraAggregatorStateOut,
    MediaBufferListEnvelope,
)


def _aggregator_envelope() -> AggregatorStateListEnvelope:
    return AggregatorStateListEnvelope(
        items=[
            CameraAggregatorStateOut(
                camera_id="cts-1",
                origin="cts",
                display_name="Kitchen CTS",
                room_name="Kitchen",
                buffer_depth=4,
                buffer_capacity=512,
                pending_flush=None,
                cooldown_remaining_seconds=None,
                rate_per_second=0.5,
                tokens_available=1.0,
                images_eligible_total=10,
                images_dropped_total=2,
                last_event_at="2026-06-14T12:00:00+00:00",
            )
        ],
        total=1,
    )


def _build_client(service: MagicMock | None, permissions: list[str]) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="test",
        name="test",
        permissions=permissions,
    )
    app.state.media_observability = service
    return TestClient(app, raise_server_exceptions=False)


def test_get_media_buffer_returns_envelope() -> None:
    service = MagicMock()
    service.media_buffer.return_value = MediaBufferListEnvelope(items=[], total=0)
    client = _build_client(service, ["*"])

    response = client.get("/api/v1/media/buffer?limit=10&offset=2")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}
    service.media_buffer.assert_called_once_with(sensor_id=None, limit=10, offset=2)


def test_get_aggregators_returns_envelope() -> None:
    service = MagicMock()
    service.aggregator_state.return_value = _aggregator_envelope()
    client = _build_client(service, ["*"])

    response = client.get("/api/v1/media/aggregators")

    assert response.status_code == 200
    assert response.json()["items"][0]["camera_id"] == "cts-1"
    assert response.json()["total"] == 1


def test_get_aggregators_requires_admin_permission() -> None:
    service = MagicMock()
    service.aggregator_state.return_value = _aggregator_envelope()
    client = _build_client(service, [])

    response = client.get("/api/v1/media/aggregators")

    assert response.status_code == 403
    service.aggregator_state.assert_not_called()


def test_get_aggregators_respects_origin_filter() -> None:
    service = MagicMock()
    service.aggregator_state.return_value = _aggregator_envelope()
    client = _build_client(service, ["*"])

    response = client.get("/api/v1/media/aggregators?origin=cts&q=kitchen")

    assert response.status_code == 200
    service.aggregator_state.assert_called_once_with(
        origin="cts",
        camera_id=None,
        room_name=None,
        query="kitchen",
        limit=50,
        offset=0,
    )


def test_get_aggregators_missing_service_returns_503() -> None:
    client = _build_client(None, ["*"])

    response = client.get("/api/v1/media/aggregators")

    assert response.status_code == 503
