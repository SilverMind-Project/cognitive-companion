"""Integration tests for info_cards, quizzes, and knowledge_interactions routers."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.routers import info_cards, knowledge_interactions, quizzes
from backend.services.knowledge.content_generation import (
    ParaphraseSuggestion,
    QuizQuestionSuggestion,
    QuizSuggestion,
)
from backend.services.knowledge.info_card_service import InfoCardService
from backend.services.knowledge.interaction_service import KnowledgeInteractionService
from backend.services.knowledge.layout_registry import LayoutRegistry
from backend.services.knowledge.quiz_service import QuizService


@pytest.fixture
def client(db_factory) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    minio = Mock()
    minio.generate_presigned_url.return_value = "http://minio.test/presigned"
    minio.async_upload_bytes = AsyncMock()

    image_pipeline = Mock()
    image_pipeline.validate_upload.return_value = (400, 300)
    image_pipeline.render_variants = AsyncMock(return_value={})
    image_pipeline.purge_prefix = AsyncMock()

    layouts = LayoutRegistry.load("config/knowledge_layouts.yaml")

    content_gen = Mock()
    content_gen.suggest_paraphrase = AsyncMock(
        return_value=ParaphraseSuggestion(
            title="Suggested Card",
            body_text="Suggested body.",
            voice_instruction="Speak gently.",
        )
    )
    content_gen.suggest_quiz = AsyncMock(
        return_value=QuizSuggestion(
            title="Suggested Quiz",
            intro_voice_template="Welcome!",
            voice_instruction="Warm tone.",
            questions=[
                QuizQuestionSuggestion(
                    question_type="open_ended",
                    question_text="Suggested Q1?",
                    expected_answer="A1",
                    explanation="Exp 1",
                )
            ],
        )
    )
    content_gen.suggest_voice_instruction = AsyncMock(return_value="Speak slowly and clearly.")
    content_gen.regenerate_question = AsyncMock(
        return_value=QuizQuestionSuggestion(
            question_type="open_ended",
            question_text="Regenerated Q?",
            expected_answer="New A",
            explanation="New Exp",
        )
    )

    app.state.minio_client = minio
    app.state.image_pipeline = image_pipeline
    app.state.layout_registry = layouts
    app.state.knowledge_content_gen = content_gen
    app.state.info_card_service = InfoCardService(
        db_factory=db_factory,
        minio_client=minio,
        image_pipeline=image_pipeline,
        layout_registry=layouts,
    )
    app.state.quiz_service = QuizService(
        db_factory=db_factory,
        minio_client=minio,
        image_pipeline=image_pipeline,
        layout_registry=layouts,
    )
    app.state.knowledge_interaction_service = KnowledgeInteractionService(
        db_factory=db_factory,
    )

    async def override_auth() -> AuthContext:
        return AuthContext(
            key="test",
            name="Test Admin",
            roles=["admin"],
            device_type=None,
            sensor_id=None,
        )

    app.dependency_overrides[get_auth_context] = override_auth

    app.include_router(info_cards.router, prefix="/api/v1")
    app.include_router(quizzes.router, prefix="/api/v1")
    app.include_router(knowledge_interactions.router, prefix="/api/v1")
    app.include_router(knowledge_interactions.analytics_router, prefix="/api/v1")
    return TestClient(app)


def test_info_cards_router_crud_and_suggest(client: TestClient) -> None:
    created = client.post(
        "/api/v1/info-cards",
        json={
            "title": "Hydration Card",
            "body_text": "Drink water.",
            "layout_id": "text_only",
            "tags": ["hydration"],
        },
    )
    assert created.status_code == 201
    card_id = created.json()["id"]

    listed = client.get("/api/v1/info-cards?tag=hydration")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    patched = client.patch(f"/api/v1/info-cards/{card_id}", json={"title": "Updated Hydration"})
    assert patched.status_code == 200
    assert patched.json()["title"] == "Updated Hydration"

    approved = client.post(f"/api/v1/info-cards/{card_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    archived = client.post(f"/api/v1/info-cards/{card_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    restored = client.post(f"/api/v1/info-cards/{card_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["status"] == "restored"

    suggested = client.post("/api/v1/info-cards/suggest?document_id=1")
    assert suggested.status_code == 200
    assert suggested.json()["title"] == "Suggested Card"

    deleted = client.delete(f"/api/v1/info-cards/{card_id}")
    assert deleted.status_code == 204


def test_quizzes_router_crud_questions_and_suggest(client: TestClient) -> None:
    created = client.post(
        "/api/v1/quizzes",
        json={
            "title": "Morning Quiz",
            "question_layout_id": "quiz_with_optional_image",
            "tags": ["morning"],
        },
    )
    assert created.status_code == 201
    quiz_id = created.json()["id"]

    q1 = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_type": "open_ended",
            "question_text": "First?",
            "expected_answer": "One",
        },
    )
    assert q1.status_code == 201
    q1_id = q1.json()["id"]

    q2 = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_type": "open_ended",
            "question_text": "Second?",
            "expected_answer": "Two",
        },
    )
    assert q2.status_code == 201
    q2_id = q2.json()["id"]

    reordered = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions/reorder",
        json={"items": [{"id": q2_id, "ord": 0}, {"id": q1_id, "ord": 1}]},
    )
    assert reordered.status_code == 200
    assert reordered.json()["status"] == "reordered"

    detail = client.get(f"/api/v1/quizzes/{quiz_id}")
    assert detail.status_code == 200
    assert [q["id"] for q in detail.json()["questions"]] == [q2_id, q1_id]

    suggested = client.post("/api/v1/quizzes/suggest?document_id=1")
    assert suggested.status_code == 200
    assert suggested.json()["title"] == "Suggested Quiz"

    deleted = client.delete(f"/api/v1/quizzes/{quiz_id}")
    assert deleted.status_code == 204


def test_knowledge_interactions_router_endpoints(client: TestClient) -> None:
    queries = client.get("/api/v1/knowledge-interactions/queries")
    assert queries.status_code == 200
    assert set(queries.json()) == {"items", "total"}
    assert isinstance(queries.json()["items"], list)

    sessions = client.get("/api/v1/knowledge-interactions/quiz-sessions")
    assert sessions.status_code == 200
    assert set(sessions.json()) == {"items", "total"}
    assert isinstance(sessions.json()["items"], list)

    deliveries = client.get("/api/v1/knowledge-interactions/info-card-deliveries")
    assert deliveries.status_code == 200
    assert set(deliveries.json()) == {"items", "total"}
    assert isinstance(deliveries.json()["items"], list)

    tags = client.get("/api/v1/knowledge/analytics/tags")
    assert tags.status_code == 200
    assert "tags" in tags.json()
