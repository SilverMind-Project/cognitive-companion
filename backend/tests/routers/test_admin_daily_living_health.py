"""Router tests for GET /api/v1/admin/daily-living-health (DL-M01)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.integrations.semantic_memory_client import ObservationsByDay
from backend.routers.admin_metrics import router
from backend.routers.dependencies import get_daily_living_health
from backend.services.daily_living_health import (
    ActivityLedgerHealth,
    ActivityTypeHealth,
    DailyLivingHealthSnapshot,
    SemanticMemoryHealth,
)

_NOW = datetime(2026, 7, 21, 14, 0, 0, tzinfo=UTC)

_SNAPSHOT = DailyLivingHealthSnapshot(
    semantic_memory=SemanticMemoryHealth(
        reachable=True,
        last_observation_at=_NOW,
        last_movement_at=_NOW,
        observations_by_day=[],
        total_observations=5,
        total_movements=2,
        stale=False,
    ),
    activity_ledger=ActivityLedgerHealth(
        by_type=[ActivityTypeHealth(activity_type="sleep", count=1, last_opened_at=_NOW)],
        stale=False,
    ),
)


def _build_app(*, service=None, permissions: list[str] = ("*",)):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)

    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=list(permissions)
    )
    if service is not None:
        app.dependency_overrides[get_daily_living_health] = lambda: service
    else:
        # Leave the real dependency in place; app.state.daily_living_health
        # is unset (None) so the 503 "service unavailable" path is exercised.
        app.state.daily_living_health = None

    return TestClient(app, raise_server_exceptions=False)


class TestDailyLivingHealthEndpoint:
    def test_200_with_service_wired(self):
        svc = AsyncMock()
        svc.snapshot = AsyncMock(return_value=_SNAPSHOT)
        client = _build_app(service=svc)

        resp = client.get("/api/v1/admin/daily-living-health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["semantic_memory"]["reachable"] is True
        assert body["semantic_memory"]["total_observations"] == 5
        assert body["activity_ledger"]["by_type"][0]["activity_type"] == "sleep"
        assert body["activity_ledger"]["stale"] is False

    def test_200_serializes_observations_by_day(self):
        """The has-data path: observations_by_day must round-trip through the
        endpoint's day.date().isoformat() transform, not just an empty list."""
        snapshot = DailyLivingHealthSnapshot(
            semantic_memory=SemanticMemoryHealth(
                reachable=True,
                last_observation_at=_NOW,
                last_movement_at=_NOW,
                observations_by_day=[
                    ObservationsByDay(day=_NOW, source="scene_intel", count=7),
                ],
                total_observations=7,
                total_movements=0,
                stale=False,
            ),
            activity_ledger=ActivityLedgerHealth(by_type=[], stale=True),
        )
        svc = AsyncMock()
        svc.snapshot = AsyncMock(return_value=snapshot)
        client = _build_app(service=svc)

        resp = client.get("/api/v1/admin/daily-living-health")

        assert resp.status_code == 200
        by_day = resp.json()["semantic_memory"]["observations_by_day"]
        assert len(by_day) == 1
        assert by_day[0]["day"] == "2026-07-21"
        assert by_day[0]["source"] == "scene_intel"
        assert by_day[0]["count"] == 7

    def test_403_without_permission(self):
        svc = AsyncMock()
        svc.snapshot = AsyncMock(return_value=_SNAPSHOT)
        client = _build_app(service=svc, permissions=[])

        resp = client.get("/api/v1/admin/daily-living-health")

        assert resp.status_code == 403

    def test_503_when_service_unavailable(self):
        client = _build_app(service=None)

        resp = client.get("/api/v1/admin/daily-living-health")

        assert resp.status_code == 503
