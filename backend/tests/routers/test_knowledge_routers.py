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
    image_pipeline.purge_objects = AsyncMock()

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


def _mc_body(text: str, choices: list[dict] | None = None) -> dict:
    return {
        "question_type": "multiple_choice",
        "question_text": text,
        "choices": choices
        or [{"id": "a", "text": "Yes", "is_correct": True}, {"id": "b", "text": "No"}],
    }


def test_quiz_created_with_its_questions_in_one_request(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/quizzes",
        json={"title": "Family", "questions": [_mc_body("Q1"), _mc_body("Q2")]},
    )

    assert resp.status_code == 201, resp.text
    assert [q["question_text"] for q in resp.json()["questions"]] == ["Q1", "Q2"]


@pytest.mark.parametrize(
    "choices",
    [
        [{"id": "", "text": "Yes"}],
        [{"id": "  ", "text": "Yes"}],
        [{"id": "a", "text": "Yes"}, {"id": "A", "text": "No"}],
    ],
)
def test_blank_or_repeated_choice_ids_are_rejected(client: TestClient, choices) -> None:
    """A null or empty id was the manual-authoring 422 the editor kept hitting; the server
    now names the problem instead of accepting ids no answer can refer to."""
    quiz = client.post("/api/v1/quizzes", json={"title": "Family"}).json()

    resp = client.post(f"/api/v1/quizzes/{quiz['id']}/questions", json=_mc_body("Q", choices))

    assert resp.status_code == 422


def test_replace_questions_route_saves_the_editor_list(client: TestClient) -> None:
    quiz = client.post(
        "/api/v1/quizzes", json={"title": "Family", "questions": [_mc_body("Q1"), _mc_body("Q2")]}
    ).json()
    _q1, q2 = quiz["questions"]

    resp = client.put(
        f"/api/v1/quizzes/{quiz['id']}/questions",
        json={"questions": [{**_mc_body("Q2"), "id": q2["id"]}, _mc_body("New")]},
    )

    assert resp.status_code == 200, resp.text
    assert [q["question_text"] for q in resp.json()["questions"]] == ["Q2", "New"]


def test_replace_that_removes_needs_delete_permission(client: TestClient) -> None:
    quiz = client.post(
        "/api/v1/quizzes", json={"title": "Family", "questions": [_mc_body("Q1"), _mc_body("Q2")]}
    ).json()
    q1 = quiz["questions"][0]

    async def write_only() -> AuthContext:
        return AuthContext(key="w", name="Writer", roles=[], tokens=frozenset({"quizzes:write"}))

    client.app.dependency_overrides[get_auth_context] = write_only
    resp = client.put(
        f"/api/v1/quizzes/{quiz['id']}/questions",
        json={"questions": [{**_mc_body("Q1"), "id": q1["id"]}]},
    )

    assert resp.status_code == 403
    assert "quizzes:delete" in resp.text


def test_patch_with_questions_saves_details_and_list_in_one_call(client: TestClient) -> None:
    quiz = client.post(
        "/api/v1/quizzes", json={"title": "Family", "questions": [_mc_body("Q1"), _mc_body("Q2")]}
    ).json()
    _q1, q2 = quiz["questions"]

    resp = client.patch(
        f"/api/v1/quizzes/{quiz['id']}",
        json={"title": "Renamed", "questions": [{**_mc_body("Q2"), "id": q2["id"]}]},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Renamed"
    assert [q["question_text"] for q in resp.json()["questions"]] == ["Q2"]


def test_patch_that_removes_questions_needs_delete_permission(client: TestClient) -> None:
    quiz = client.post(
        "/api/v1/quizzes", json={"title": "Family", "questions": [_mc_body("Q1"), _mc_body("Q2")]}
    ).json()
    q1 = quiz["questions"][0]

    async def write_only() -> AuthContext:
        return AuthContext(key="w", name="Writer", roles=[], tokens=frozenset({"quizzes:write"}))

    full_access = client.app.dependency_overrides.get(get_auth_context)
    client.app.dependency_overrides[get_auth_context] = write_only
    resp = client.patch(
        f"/api/v1/quizzes/{quiz['id']}",
        json={"title": "Renamed", "questions": [{**_mc_body("Q1"), "id": q1["id"]}]},
    )
    client.app.dependency_overrides[get_auth_context] = full_access

    assert resp.status_code == 403
    # Refused under the lock with the details: the new title was not saved either.
    assert client.get(f"/api/v1/quizzes/{quiz['id']}").json()["title"] == "Family"


def test_incomplete_reorder_is_422_not_500(client: TestClient) -> None:
    quiz = client.post(
        "/api/v1/quizzes", json={"title": "Family", "questions": [_mc_body("Q1"), _mc_body("Q2")]}
    ).json()
    q2 = quiz["questions"][1]

    resp = client.post(
        f"/api/v1/quizzes/{quiz['id']}/questions/reorder",
        json={"items": [{"id": q2["id"], "ord": 0}]},
    )

    assert resp.status_code == 422


def test_repeated_tag_parameters_match_any_tag(client: TestClient) -> None:
    for title, tags in (("Meds", ["medication"]), ("Kin", ["family"]), ("Other", ["garden"])):
        client.post("/api/v1/quizzes", json={"title": title, "tags": tags})

    resp = client.get("/api/v1/quizzes", params=[("tag", "medication"), ("tag", "family")])

    assert sorted(q["title"] for q in resp.json()["items"]) == ["Kin", "Meds"]
    assert resp.json()["total"] == 2
