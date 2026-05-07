"""Integration tests for knowledge layouts router."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.core.exceptions import register_exception_handlers
from backend.routers.knowledge_layouts import router
from backend.services.knowledge.layout_registry import LayoutRegistry


@pytest.fixture
def layout_registry():
    return LayoutRegistry.load("config/knowledge_layouts.yaml")


@pytest.fixture
def client(layout_registry):
    app = FastAPI()
    register_exception_handlers(app)

    # Override auth
    async def override_auth():
        from backend.core.auth import AuthContext
        return AuthContext(key="test", name="Test", permissions=["*"], device_type=None, sensor_id=None)

    from backend.core.auth import get_auth_context
    app.dependency_overrides[get_auth_context] = override_auth

    # Store registry on app state
    app.state.layout_registry = layout_registry

    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


class TestKnowledgeLayouts:
    def test_list_all_layouts(self, client):
        resp = client.get("/api/v1/knowledge/layouts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["layouts"]) == 5

    def test_filter_by_applies_to(self, client):
        resp = client.get("/api/v1/knowledge/layouts?applies_to=info_card")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["layouts"]) == 4

    def test_get_single_layout(self, client):
        resp = client.get("/api/v1/knowledge/layouts/text_only")
        assert resp.status_code == 200
        assert resp.json()["id"] == "text_only"

    def test_404_unknown_layout(self, client):
        resp = client.get("/api/v1/knowledge/layouts/nonexistent")
        assert resp.status_code == 404
