"""Service-layer tests for QuizService."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
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
    pipeline.purge_objects = AsyncMock()
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


def _mc(text: str, *, correct: bool = True) -> dict:
    return {
        "question_type": "multiple_choice",
        "question_text": text,
        "choices": [
            {"id": "a", "text": "Yes", "is_correct": correct},
            {"id": "b", "text": "No", "is_correct": False},
        ],
    }


def test_approve_quiz_rejects_empty_questions_or_invalid_choices(
    quiz_service: QuizService,
) -> None:
    empty = quiz_service.create_quiz({"title": "Empty"})
    with pytest.raises(ConflictError, match="0 questions"):
        quiz_service.approve_quiz(empty["id"], approved_by="Caregiver")

    no_correct = quiz_service.create_quiz(
        {"title": "No answer", "questions": [_mc("Is it Sunday?", correct=False)]}
    )
    with pytest.raises(ConflictError, match="Question 1 must have at least 2 choices"):
        quiz_service.approve_quiz(no_correct["id"], approved_by="Caregiver")

    open_ended = quiz_service.create_quiz(
        {
            "title": "Open",
            "questions": [{"question_type": "open_ended", "question_text": "Favourite tea?"}],
        }
    )
    with pytest.raises(ConflictError, match="non-empty expected answer"):
        quiz_service.approve_quiz(open_ended["id"], approved_by="Caregiver")
    assert quiz_service.get_quiz(open_ended["id"])["status"] == "draft"

    valid = quiz_service.create_quiz({"title": "Valid", "questions": [_mc("Is it Sunday?")]})
    assert quiz_service.approve_quiz(valid["id"], approved_by="Caregiver")["status"] == "approved"


async def test_delete_quiz_raises_409_when_referenced_by_active_rule_or_session(
    quiz_service: QuizService, image_pipeline: Mock, db_session
) -> None:
    from backend.models.knowledge import QuizSession
    from backend.models.pipeline import PipelineStep
    from backend.models.rule import Rule

    used = quiz_service.create_quiz({"title": "Used", "questions": [_mc("Q?")]})
    rule = Rule(name="morning quiz", enabled=True)
    db_session.add(rule)
    db_session.flush()
    db_session.add(
        PipelineStep(rule_id=rule.id, step_type="quiz_start", config_json={"quiz_id": used["id"]})
    )
    db_session.commit()
    with pytest.raises(ConflictError, match="used by rule"):
        await quiz_service.delete_quiz(used["id"])

    played = quiz_service.create_quiz({"title": "Played", "questions": [_mc("Q?")]})
    db_session.add(QuizSession(quiz_id=played["id"], status="completed"))
    db_session.commit()
    with pytest.raises(ConflictError, match="1 session record"):
        await quiz_service.delete_quiz(played["id"])
    assert len(quiz_service.get_quiz(played["id"])["questions"]) == 1

    unused = quiz_service.create_quiz({"title": "Unused", "questions": [_mc("Q?")]})
    await quiz_service.delete_quiz(unused["id"])
    image_pipeline.purge_prefix.assert_awaited_once_with(f"quizzes/{unused['id']}/")


async def test_delete_question_raises_409_when_responses_exist_and_compacts_ord_when_unanswered(
    quiz_service: QuizService, image_pipeline: Mock, db_session
) -> None:
    from backend.models.knowledge import QuizResponse, QuizSession

    quiz = quiz_service.create_quiz(
        {"title": "Family", "questions": [_mc("First?"), _mc("Second?"), _mc("Third?")]}
    )
    first, second, third = quiz["questions"]

    session = QuizSession(quiz_id=quiz["id"], status="completed")
    db_session.add(session)
    db_session.flush()
    db_session.add(
        QuizResponse(
            session_id=session.id,
            question_id=first["id"],
            question_ord=0,
            question_text="First?",
            channel="pwa",
        )
    )
    db_session.commit()

    with pytest.raises(ConflictError, match="1 recorded response"):
        await quiz_service.delete_question(quiz["id"], first["id"])

    await quiz_service.delete_question(quiz["id"], second["id"])

    remaining = quiz_service.get_quiz(quiz["id"])["questions"]
    assert [(q["id"], q["ord"]) for q in remaining] == [(first["id"], 0), (third["id"], 1)]
    image_pipeline.purge_prefix.assert_awaited_once_with(f"quizzes/{quiz['id']}/q{second['id']}__")


async def test_set_question_image_from_source_image_id_renders_variants_and_presigns_url(
    quiz_service: QuizService, image_pipeline: Mock, minio_client: Mock, db_session
) -> None:
    from backend.models.knowledge import KnowledgeDocument, KnowledgeDocumentImage
    from backend.services.knowledge.image_pipeline import RenderedVariant

    doc = KnowledgeDocument(title="Album", source_text="Photos", tags=[], created_by="cg")
    db_session.add(doc)
    db_session.flush()
    src = KnowledgeDocumentImage(
        document_id=doc.id,
        minio_object_name=f"knowledge/{doc.id}/img-0.jpg",
        mime_type="image/jpeg",
        width=400,
        height=300,
        alt_text="Priya",
        ord=0,
    )
    db_session.add(src)
    db_session.commit()

    quiz = quiz_service.create_quiz({"title": "Faces", "questions": [_mc("Who is this?")]})
    qid = quiz["questions"][0]["id"]
    key = f"quizzes/{quiz['id']}/q{qid}"
    image_pipeline.render_variants.return_value = {
        "pwa": RenderedVariant(
            object_name=f"{key}__pwa.webp",
            width=400,
            height=300,
            format="webp",
            size_bytes=10,
            generated_at="2026-11-22T00:00:00+00:00",
        )
    }

    out = await quiz_service.set_question_image(
        quiz["id"],
        qid,
        file_bytes=None,
        content_type=None,
        source_image_id=src.id,
        alt_text="Priya at the beach",
    )

    render = image_pipeline.render_variants.await_args.kwargs
    assert render["original_object_name"] == src.minio_object_name
    assert render["target_key_prefix"] == key
    slot = out["image_slot"]
    assert slot["source_image_id"] == src.id
    assert slot["original_object_name"] == src.minio_object_name
    assert slot["variants"]["pwa"]["object_name"] == f"{key}__pwa.webp"
    assert slot["variants"]["pwa"]["presigned_url"] == "http://minio.test/presigned"

    # Clearing the image purges only the quiz-owned variant, never the document's original.
    await quiz_service.delete_question_image(quiz["id"], qid)
    purged = set(image_pipeline.purge_objects.await_args.args[0])
    assert purged == {f"{key}__pwa.webp"}


async def test_set_question_image_requires_a_source(quiz_service: QuizService) -> None:
    quiz = quiz_service.create_quiz({"title": "Faces", "questions": [_mc("Who?")]})
    with pytest.raises(ValidationError):
        await quiz_service.set_question_image(
            quiz["id"],
            quiz["questions"][0]["id"],
            file_bytes=None,
            content_type=None,
            source_image_id=None,
            alt_text="",
        )
