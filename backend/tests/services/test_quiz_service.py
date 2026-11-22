"""Service-layer tests for QuizService."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from backend.core.exceptions import NotFoundError
from backend.services.knowledge.layout_registry import LayoutRegistry
from backend.services.knowledge.quiz_service import QuizService


@pytest.fixture
def layout_registry() -> LayoutRegistry:
    return LayoutRegistry.load("config/knowledge_layouts.yaml")


@pytest.fixture
def minio_client() -> Mock:
    minio = Mock()
    minio.generate_presigned_url.return_value = "http://minio.test/presigned"
    minio.async_upload_bytes = AsyncMock()
    return minio


@pytest.fixture
def image_pipeline() -> Mock:
    pipeline = Mock()
    pipeline.validate_upload.return_value = (400, 300)
    pipeline.render_variants = AsyncMock(return_value={})
    pipeline.purge_prefix = AsyncMock()
    return pipeline


@pytest.fixture
def quiz_service(
    db_factory, minio_client: Mock, image_pipeline: Mock, layout_registry: LayoutRegistry
) -> QuizService:
    return QuizService(
        db_factory=db_factory,
        minio_client=minio_client,
        image_pipeline=image_pipeline,
        layout_registry=layout_registry,
    )


def test_create_quiz_with_questions_and_get(quiz_service: QuizService) -> None:
    quiz = quiz_service.create_quiz(
        {
            "title": "Family Memories",
            "question_layout_id": "quiz_with_optional_image",
            "intro_voice_template": "Let's reminisce together.",
            "tags": ["family"],
            "questions": [
                {
                    "question_type": "multiple_choice",
                    "question_text": "Where does Priya live?",
                    "choices": [
                        {"id": "a", "text": "Boston", "is_correct": True},
                        {"id": "b", "text": "Seattle", "is_correct": False},
                    ],
                    "explanation": "Priya moved to Boston in 2022.",
                },
                {
                    "question_type": "open_ended",
                    "question_text": "What is your favorite tea?",
                    "expected_answer": "Masala chai",
                    "explanation": "You enjoy masala chai every afternoon.",
                },
            ],
        }
    )
    quiz_id = quiz["id"]
    assert quiz["title"] == "Family Memories"
    assert len(quiz["questions"]) == 2
    assert quiz["questions"][0]["ord"] == 0
    assert quiz["questions"][1]["ord"] == 1

    fetched = quiz_service.get_quiz(quiz_id)
    assert len(fetched["questions"]) == 2
    assert fetched["questions"][0]["question_text"] == "Where does Priya live?"

    listed = quiz_service.list_quizzes(status="draft", tag="family")
    assert listed["total"] == 1
    assert listed["items"][0]["question_count"] == 2


def test_reorder_questions_atomic_no_unique_collision(quiz_service: QuizService) -> None:
    quiz = quiz_service.create_quiz(
        {
            "title": "Reorder Test",
            "question_layout_id": "quiz_with_optional_image",
        }
    )
    quiz_id = quiz["id"]
    q0 = quiz_service.add_question(
        quiz_id,
        {
            "question_type": "open_ended",
            "question_text": "First question",
            "expected_answer": "A",
        },
    )
    q1 = quiz_service.add_question(
        quiz_id,
        {
            "question_type": "open_ended",
            "question_text": "Second question",
            "expected_answer": "B",
        },
    )
    assert q0["ord"] == 0
    assert q1["ord"] == 1

    reordered = quiz_service.reorder_questions(
        quiz_id,
        [
            {"id": q1["id"], "ord": 0},
            {"id": q0["id"], "ord": 1},
        ],
    )
    assert [q["id"] for q in reordered] == [q1["id"], q0["id"]]
    assert [q["ord"] for q in reordered] == [0, 1]


async def test_update_approved_quiz_bumps_version(
    quiz_service: QuizService, image_pipeline: Mock
) -> None:
    quiz = quiz_service.create_quiz(
        {
            "title": "Initial Title",
            "question_layout_id": "quiz_with_optional_image",
        }
    )
    quiz_id = quiz["id"]
    q = quiz_service.add_question(
        quiz_id,
        {
            "question_type": "open_ended",
            "question_text": "Question 1",
            "expected_answer": "Answer 1",
        },
    )

    approved = quiz_service.approve_quiz(quiz_id, approved_by="Caregiver Admin")
    assert approved["status"] == "approved"
    assert approved["version"] == 2

    updated = quiz_service.update_quiz(quiz_id, {"title": "Updated Title"})
    assert updated["version"] == 3

    quiz_service.update_question(quiz_id, q["id"], {"question_text": "Updated Question 1"})
    after_q_edit = quiz_service.get_quiz(quiz_id)
    assert after_q_edit["version"] == 4

    await quiz_service.delete_quiz(quiz_id)
    image_pipeline.purge_prefix.assert_awaited_once_with(f"quizzes/{quiz_id}/")
    with pytest.raises(NotFoundError):
        quiz_service.get_quiz(quiz_id)
