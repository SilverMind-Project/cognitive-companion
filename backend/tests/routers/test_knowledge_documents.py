"""Integration tests for knowledge document router."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext
from backend.core.exceptions import register_exception_handlers
from backend.routers.knowledge import router
from backend.services.knowledge.ingestion_service import KnowledgeIngestionService


@pytest.fixture
def client(db_factory):
    app = FastAPI()
    register_exception_handlers(app)
    minio = Mock()
    minio.generate_presigned_url.return_value = None
    image_pipeline = Mock()
    app.state.minio_client = minio
    app.state.knowledge_ingestion = KnowledgeIngestionService(
        db_factory=db_factory,
        minio_client=minio,
        image_pipeline=image_pipeline,
    )

    # Override auth with admin context
    async def override_auth():
        return AuthContext(
            key="test", name="Test Admin", permissions=["*"], device_type=None, sensor_id=None
        )

    from backend.core.auth import get_auth_context

    app.dependency_overrides[get_auth_context] = override_auth

    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


class TestKnowledgeDocuments:
    def test_list_empty(self, client):
        resp = client.get("/api/v1/knowledge/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_create_document(self, client):
        resp = client.post(
            "/api/v1/knowledge/documents",
            data={
                "title": "Test Doc",
                "source_text": "This is a test document.",
                "tags": "family,test",
            },
        )
        assert resp.status_code == 201
        doc = resp.json()
        assert doc["title"] == "Test Doc"
        assert doc["source_text"] == "This is a test document."
        assert doc["status"] == "uploaded"
        assert "family" in doc["tags"]
        assert "test" in doc["tags"]

    def test_get_document(self, client):
        resp = client.post(
            "/api/v1/knowledge/documents",
            data={"title": "Get Test", "source_text": "content", "tags": ""},
        )
        doc_id = resp.json()["id"]
        resp = client.get(f"/api/v1/knowledge/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Get Test"

    def test_approve_document(self, client):
        resp = client.post(
            "/api/v1/knowledge/documents",
            data={"title": "Approve Test", "source_text": "content", "tags": ""},
        )
        doc_id = resp.json()["id"]
        resp = client.post(f"/api/v1/knowledge/documents/{doc_id}/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_archive_and_restore(self, client):
        resp = client.post(
            "/api/v1/knowledge/documents",
            data={"title": "Archive Test", "source_text": "content", "tags": ""},
        )
        doc_id = resp.json()["id"]
        resp = client.post(f"/api/v1/knowledge/documents/{doc_id}/archive")
        assert resp.json()["status"] == "archived"
        resp = client.post(f"/api/v1/knowledge/documents/{doc_id}/restore")
        assert resp.json()["status"] == "uploaded"

    def test_list_filters_by_status(self, client):
        client.post(
            "/api/v1/knowledge/documents", data={"title": "A", "source_text": "x", "tags": ""}
        )
        client.post(
            "/api/v1/knowledge/documents", data={"title": "B", "source_text": "x", "tags": ""}
        )
        resp = client.get("/api/v1/knowledge/documents?status=uploaded")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 2

    def test_404_not_found(self, client):
        resp = client.get("/api/v1/knowledge/documents/99999")
        assert resp.status_code == 404
