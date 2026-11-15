"""Review, correction, visitor, and quiz-approval actions are attributed to the API key's name.

These routes once read ``request.state.auth_context``, which nothing sets, so every ReID review,
PH correction, and visitor decision was recorded as "system" and every quiz approval as NULL.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, actor_from_auth, get_auth_context
from backend.core.config import Settings
from backend.core.database import get_db
from backend.core.exceptions import AuthenticationError, register_exception_handlers
from backend.routers import cts_ph, cts_reid_review, quizzes, visitors
from backend.routers.dependencies import (
    get_config_minio_client,
    get_orchestrator_client,
    get_reid_review_service,
    get_visitor_admin_service,
)
from backend.schemas.cts_reid_review import ReviewCandidateView
from backend.schemas.visitors import DismissVisitorResponse

_KEY_NAME = "Caregiver Admin"


def _app(router, *, authenticated: bool = True) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    if authenticated:
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(
            key="x", name=_KEY_NAME, permissions=["*"]
        )
    return app


@pytest.fixture(autouse=True)
def _cts_enabled():
    with patch("backend.routers.cts_deps.settings", Settings.from_dict({"cts": {"enabled": True}})):
        yield


def test_actor_is_the_key_name() -> None:
    assert actor_from_auth(AuthContext(key="k", name=_KEY_NAME)) == _KEY_NAME


@pytest.mark.parametrize("auth", [None, AuthContext(key="k", name="")])
def test_an_unnamed_or_missing_caller_is_never_recorded(auth: AuthContext | None) -> None:
    with pytest.raises(AuthenticationError):
        actor_from_auth(auth)


def _reid_candidate() -> ReviewCandidateView:
    return ReviewCandidateView(
        candidate_id="c1",
        identity_id="m1",
        proposed_identity_id="m1",
        effective_identity_id="m1",
        person_id="m1",
        state="operator_verified",
        candidate_reason="face_derived",
        model_version="v1",
        preprocessing_version="v1",
        orientation=0,
        quality=0.8,
        is_truncated=False,
        is_occluded=False,
        audit_version=2,
        crop_url=None,
        frame_url=None,
    )


def test_reid_approval_records_the_key_name() -> None:
    svc = MagicMock()
    svc.approve = AsyncMock(return_value=_reid_candidate())
    app = _app(cts_reid_review.router)
    app.dependency_overrides[get_reid_review_service] = lambda: svc

    response = TestClient(app).post(
        "/api/v1/cts/identity/reid-review/candidates/c1/approve", json={"base_audit_version": 1}
    )

    assert response.status_code == 200
    assert svc.approve.await_args.kwargs["actor"] == _KEY_NAME


def test_ph_correction_sends_the_key_name_to_cts() -> None:
    client = AsyncMock()
    client.correct_ph_identity.return_value = {"revision": {"revision_id": "r1", "ph_id": "p1"}}
    app = _app(cts_ph.router)
    app.dependency_overrides[get_orchestrator_client] = lambda: client

    response = TestClient(app).post(
        "/api/v1/cts/ph/p1/correct", json={"new_identity_id": "m1", "reason": "wrong_person"}
    )

    assert response.status_code == 200
    assert client.correct_ph_identity.await_args.kwargs["actor"] == _KEY_NAME


def test_visitor_dismissal_logs_the_key_name() -> None:
    svc = MagicMock()
    svc.dismiss_cluster = AsyncMock(
        return_value=DismissVisitorResponse(cluster_id="v1", status="dismissed")
    )
    app = _app(visitors.router)
    app.dependency_overrides[get_visitor_admin_service] = lambda: svc
    app.dependency_overrides[get_config_minio_client] = lambda: MagicMock()

    with patch.object(visitors, "logger") as logger:
        response = TestClient(app).post("/api/v1/visitors/clusters/v1/dismiss")

    assert response.status_code == 200
    logger.info.assert_called_once_with("visitor_cluster_dismissed", cluster_id="v1", actor=_KEY_NAME)


def test_quiz_approval_stores_the_key_name() -> None:
    quiz = SimpleNamespace(
        id=1,
        document_id=None,
        title="Quiz",
        question_layout_id="quiz-default",
        intro_voice_template="",
        voice_instruction="",
        tags=[],
        status="draft",
        version=1,
        approved_by=None,
        approved_at=None,
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
        updated_at=datetime(2026, 11, 1, tzinfo=UTC),
        questions=[],
    )
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = quiz
    app = _app(quizzes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.state.minio_client = MagicMock()

    response = TestClient(app).post("/api/v1/quizzes/1/approve")

    assert response.status_code == 200
    assert quiz.approved_by == _KEY_NAME
    assert response.json()["approved_by"] == _KEY_NAME


def test_an_unauthenticated_review_is_rejected_before_any_actor_is_computed() -> None:
    svc = MagicMock()
    svc.approve = AsyncMock(return_value=_reid_candidate())
    app = _app(cts_reid_review.router, authenticated=False)
    app.dependency_overrides[get_reid_review_service] = lambda: svc

    response = TestClient(app).post(
        "/api/v1/cts/identity/reid-review/candidates/c1/approve", json={"base_audit_version": 1}
    )

    assert response.status_code == 401
    svc.approve.assert_not_awaited()
