"""BFF/MCP parity for knowledge interaction history, plus query-id capture on RAG answers."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.mcp import server as mcp
from backend.models.knowledge import KnowledgeDocument, Quiz, QuizSession, SeniorKnowledgeQuery
from backend.routers import knowledge_interactions
from backend.services.knowledge.interaction_service import KnowledgeInteractionService
from backend.services.knowledge.query_service import KnowledgeAnswer

_NOW = datetime(2026, 11, 22, 14, 0, tzinfo=UTC)


@pytest.fixture
def interaction_service(db_factory, db_session) -> KnowledgeInteractionService:
    db_session.add_all(
        [
            KnowledgeDocument(
                title="Family",
                source_text="Priya lives in Boston.",
                tags=["family"],
                status="approved",
                created_by="caregiver",
            ),
            SeniorKnowledgeQuery(
                asked_at=_NOW,
                senior_id="senior-1",
                query_text="Where does Priya live?",
                answer_text="Boston.",
                source_document_ids=[1],
                source_chunk_ids=[1],
                top_similarity=0.9,
                answered_via="rag",
                channel="voice",
            ),
        ]
    )
    quiz = Quiz(title="Family", question_layout_id="quiz_with_optional_image", tags=["family"])
    db_session.add(quiz)
    db_session.flush()
    db_session.add(QuizSession(quiz_id=quiz.id, senior_id="senior-1", status="completed"))
    db_session.commit()
    return KnowledgeInteractionService(db_factory=db_factory)


@pytest.fixture
def client(interaction_service: KnowledgeInteractionService):
    original = mcp._svc.knowledge_interaction_service
    mcp._svc.knowledge_interaction_service = interaction_service
    app = FastAPI()
    register_exception_handlers(app)
    app.state.knowledge_interaction_service = interaction_service
    app.include_router(knowledge_interactions.router, prefix="/api/v1")
    app.include_router(knowledge_interactions.analytics_router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="k", name="Caregiver", roles=["admin"]
    )
    yield TestClient(app)
    mcp._svc.knowledge_interaction_service = original


async def test_senior_query_history_parity(client: TestClient) -> None:
    bff = client.get("/api/v1/knowledge-interactions/queries", params={"senior_id": "senior-1"})
    tool = await mcp.list_senior_knowledge_queries(senior_id="senior-1")

    assert bff.status_code == 200
    assert bff.json()["total"] == tool["total"] == 1
    assert [q["id"] for q in bff.json()["items"]] == [q["id"] for q in tool["items"]]
    assert bff.json()["items"][0]["query_text"] == tool["items"][0]["query_text"]


async def test_quiz_session_history_parity(client: TestClient) -> None:
    bff = client.get("/api/v1/knowledge-interactions/quiz-sessions", params={"status": "completed"})
    tool = await mcp.list_quiz_sessions_history(status="completed")

    assert bff.status_code == 200
    assert bff.json()["total"] == tool["total"] == 1
    assert [s["id"] for s in bff.json()["items"]] == [s["id"] for s in tool["items"]]


async def test_tag_analytics_parity(client: TestClient) -> None:
    bff = client.get("/api/v1/knowledge/analytics/tags")
    tool = await mcp.get_quiz_tag_analytics()

    assert bff.status_code == 200
    assert bff.json() == tool


async def test_interaction_tools_report_missing_service() -> None:
    original = mcp._svc.knowledge_interaction_service
    mcp._svc.knowledge_interaction_service = None
    try:
        assert "error" in await mcp.list_senior_knowledge_queries()
        assert "error" in await mcp.list_quiz_sessions_history()
        assert "error" in await mcp.get_quiz_tag_analytics()
    finally:
        mcp._svc.knowledge_interaction_service = original


async def test_query_knowledge_base_routes_the_logged_query_id_to_asking_surface() -> None:
    from backend.services.interactive_session.tagging import active_tool_surface_id

    answer = KnowledgeAnswer(
        query_text="Where does Priya live?",
        answer_text="Priya lives in Boston.",
        source_document_ids=(1,),
        source_chunk_ids=(1,),
        top_similarity=0.9,
        answered_via="rag",
    )
    query_svc = MagicMock()
    query_svc.answer = AsyncMock(return_value=answer)
    query_svc.log_query.return_value = 42
    ws = MagicMock()
    ws.send_to_surface = AsyncMock()
    originals = (mcp._svc.knowledge_query, mcp._svc.ws_manager)
    mcp._svc.knowledge_query, mcp._svc.ws_manager = query_svc, ws
    token = active_tool_surface_id.set("kitchen-tablet")
    try:
        result = await mcp.query_knowledge_base("Where does Priya live?")
    finally:
        active_tool_surface_id.reset(token)
        mcp._svc.knowledge_query, mcp._svc.ws_manager = originals

    assert result["found"] is True
    surface_id, payload = ws.send_to_surface.await_args.args
    assert surface_id == "kitchen-tablet"
    assert payload["query_id"] == 42
