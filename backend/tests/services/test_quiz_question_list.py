"""Whole-list question replacement and strict reordering (real database)."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from backend.core.exceptions import ConflictError, PermissionDeniedError, ValidationError
from backend.models.knowledge import Quiz, QuizQuestion, QuizResponse, QuizSession
from backend.services.knowledge.layout_registry import LayoutRegistry
from backend.services.knowledge.quiz_service import QuizService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def image_pipeline() -> Mock:
    pipeline = Mock()
    pipeline.purge_prefix = AsyncMock()
    pipeline.purge_objects = AsyncMock()
    return pipeline


@pytest.fixture
def svc(db_factory, image_pipeline: Mock) -> QuizService:
    minio = Mock()
    minio.generate_presigned_url.return_value = "http://minio.test/presigned"
    return QuizService(
        db_factory=db_factory,
        minio_client=minio,
        image_pipeline=image_pipeline,
        layout_registry=LayoutRegistry.load("config/knowledge_layouts.yaml"),
    )


def _mc(text: str) -> dict:
    return {
        "question_type": "multiple_choice",
        "question_text": text,
        "choices": [
            {"id": "a", "text": "Yes", "is_correct": True},
            {"id": "b", "text": "No", "is_correct": False},
        ],
    }


def _quiz(svc: QuizService, *texts: str) -> dict:
    return svc.create_quiz({"title": "Family", "questions": [_mc(t) for t in texts]})


def _texts(quiz: dict) -> list[str]:
    return [q["question_text"] for q in quiz["questions"]]


async def test_replace_updates_creates_deletes_and_orders_in_one_call(svc: QuizService) -> None:
    quiz = _quiz(svc, "Q1", "Q2", "Q3")
    q1, q2, _q3 = quiz["questions"]

    out = await svc.replace_questions(
        quiz["id"],
        [
            {**_mc("New first"), "id": None},
            {**_mc("Q2 edited"), "id": q2["id"]},
            {**_mc("Q1"), "id": q1["id"]},
        ],
    )

    assert _texts(out) == ["New first", "Q2 edited", "Q1"]
    assert [q["ord"] for q in out["questions"]] == [0, 1, 2]
    assert out["questions"][1]["id"] == q2["id"]
    assert len(svc.get_quiz(quiz["id"])["questions"]) == 3  # Q3 deleted


async def test_answered_question_blocks_the_whole_replace(svc: QuizService, db_session) -> None:
    """Nothing may change when one removal is refused: the old per-request save deleted
    some questions before failing on another."""
    quiz = _quiz(svc, "Q1", "Q2")
    q1, q2 = quiz["questions"]
    session = QuizSession(quiz_id=quiz["id"], status="completed")
    db_session.add(session)
    db_session.flush()
    db_session.add(
        QuizResponse(
            session_id=session.id,
            question_id=q1["id"],
            question_ord=0,
            question_text="Q1",
            channel="pwa",
        )
    )
    db_session.commit()

    with pytest.raises(ConflictError, match=f"question {q1['id']} \\(1 answer"):
        await svc.replace_questions(quiz["id"], [{**_mc("Q2 changed"), "id": q2["id"]}])

    assert _texts(svc.get_quiz(quiz["id"])) == ["Q1", "Q2"]


async def test_unknown_or_repeated_ids_are_rejected(svc: QuizService) -> None:
    quiz = _quiz(svc, "Q1")
    other = _quiz(svc, "Elsewhere")
    q1 = quiz["questions"][0]

    with pytest.raises(ValidationError, match="not in quiz"):
        await svc.replace_questions(quiz["id"], [{**_mc("x"), "id": other["questions"][0]["id"]}])
    with pytest.raises(ValidationError, match="more than once"):
        await svc.replace_questions(
            quiz["id"], [{**_mc("x"), "id": q1["id"]}, {**_mc("y"), "id": q1["id"]}]
        )


async def test_removal_without_delete_permission_is_refused(svc: QuizService) -> None:
    quiz = _quiz(svc, "Q1", "Q2")
    q1 = quiz["questions"][0]

    with pytest.raises(PermissionDeniedError):
        await svc.replace_questions(quiz["id"], [{**_mc("Q1"), "id": q1["id"]}], allow_delete=False)
    # Keeping every question needs no delete permission.
    out = await svc.replace_questions(
        quiz["id"],
        [{**_mc("Q2"), "id": quiz["questions"][1]["id"]}, {**_mc("Q1"), "id": q1["id"]}],
        allow_delete=False,
    )
    assert _texts(out) == ["Q2", "Q1"]


async def test_replace_bumps_an_approved_quiz_version_and_purges_removed_images(
    svc: QuizService, db_session, image_pipeline: Mock
) -> None:
    quiz = _quiz(svc, "Q1", "Q2")
    approved_version = svc.approve_quiz(quiz["id"], approved_by="tester")["version"]
    q1, q2 = quiz["questions"]

    await svc.replace_questions(quiz["id"], [{**_mc("Q1"), "id": q1["id"]}])

    db_session.expire_all()
    assert db_session.get(Quiz, quiz["id"]).version == approved_version + 1
    image_pipeline.purge_prefix.assert_any_await(f"quizzes/{quiz['id']}/q{q2['id']}__")


async def test_replace_keeps_a_kept_question_image(svc: QuizService, db_session) -> None:
    quiz = _quiz(svc, "Q1")
    q1 = quiz["questions"][0]
    row = db_session.get(QuizQuestion, q1["id"])
    row.image_slot = {"alt_text": "Priya", "variants": {}}
    db_session.commit()

    await svc.replace_questions(quiz["id"], [{**_mc("Q1 edited"), "id": q1["id"]}])

    db_session.expire_all()
    assert db_session.get(QuizQuestion, q1["id"]).image_slot["alt_text"] == "Priya"


def test_reorder_requires_the_complete_order(svc: QuizService) -> None:
    quiz = _quiz(svc, "Q1", "Q2", "Q3")
    ids = [q["id"] for q in quiz["questions"]]

    with pytest.raises(ValidationError, match="every question"):
        svc.reorder_questions(quiz["id"], [{"id": ids[1], "ord": 0}, {"id": ids[0], "ord": 1}])
    with pytest.raises(ValidationError, match="every question"):
        svc.reorder_questions(quiz["id"], [{"id": i, "ord": n + 1} for n, i in enumerate(ids)])

    out = svc.reorder_questions(
        quiz["id"], [{"id": ids[2], "ord": 0}, {"id": ids[0], "ord": 1}, {"id": ids[1], "ord": 2}]
    )
    assert [q["question_text"] for q in out] == ["Q3", "Q1", "Q2"]


def test_reorder_bumps_an_approved_quiz_version(svc: QuizService, db_session) -> None:
    quiz = _quiz(svc, "Q1", "Q2")
    approved_version = svc.approve_quiz(quiz["id"], approved_by="tester")["version"]
    ids = [q["id"] for q in quiz["questions"]]

    svc.reorder_questions(quiz["id"], [{"id": ids[1], "ord": 0}, {"id": ids[0], "ord": 1}])

    db_session.expire_all()
    assert db_session.get(Quiz, quiz["id"]).version == approved_version + 1


async def test_quiz_update_saves_details_and_questions_together(svc: QuizService) -> None:
    quiz = _quiz(svc, "Q1", "Q2")
    _q1, q2 = quiz["questions"]

    out = await svc.update_quiz_with_questions(
        quiz["id"],
        {"title": "Family, revised", "tags": ["family"]},
        [{**_mc("Q2"), "id": q2["id"]}, {**_mc("Q3"), "id": None}],
    )

    assert out["title"] == "Family, revised"
    assert _texts(out) == ["Q2", "Q3"]
    assert svc.get_quiz(quiz["id"])["tags"] == ["family"]


async def test_refused_question_list_rolls_back_the_detail_changes(
    svc: QuizService, db_session
) -> None:
    """The point of one call: a refused question list must not leave the new title saved."""
    quiz = _quiz(svc, "Q1", "Q2")
    q1, q2 = quiz["questions"]
    session = QuizSession(quiz_id=quiz["id"], status="completed")
    db_session.add(session)
    db_session.flush()
    db_session.add(
        QuizResponse(
            session_id=session.id,
            question_id=q1["id"],
            question_ord=0,
            question_text="Q1",
            channel="pwa",
        )
    )
    db_session.commit()

    with pytest.raises(ConflictError):
        await svc.update_quiz_with_questions(
            quiz["id"], {"title": "Renamed"}, [{**_mc("Q2"), "id": q2["id"]}]
        )

    saved = svc.get_quiz(quiz["id"])
    assert saved["title"] == "Family"
    assert _texts(saved) == ["Q1", "Q2"]


async def test_quiz_update_bumps_an_approved_version_once(svc: QuizService, db_session) -> None:
    quiz = _quiz(svc, "Q1")
    approved_version = svc.approve_quiz(quiz["id"], approved_by="tester")["version"]
    (q1,) = quiz["questions"]

    await svc.update_quiz_with_questions(
        quiz["id"], {"title": "Renamed"}, [{**_mc("Q1 edited"), "id": q1["id"]}]
    )

    db_session.expire_all()
    assert db_session.get(Quiz, quiz["id"]).version == approved_version + 1


async def test_quiz_update_without_questions_leaves_them_untouched(
    svc: QuizService, image_pipeline: Mock
) -> None:
    quiz = _quiz(svc, "Q1", "Q2")

    out = await svc.update_quiz_with_questions(quiz["id"], {"title": "Renamed"}, None)

    assert out["title"] == "Renamed"
    assert _texts(out) == ["Q1", "Q2"]
    image_pipeline.purge_objects.assert_not_awaited()


async def test_quiz_update_rejects_an_unknown_layout_before_touching_the_quiz(
    svc: QuizService,
) -> None:
    quiz = _quiz(svc, "Q1")

    with pytest.raises(ValidationError):
        await svc.update_quiz_with_questions(
            quiz["id"], {"title": "Renamed", "question_layout_id": "no_such_layout"}, []
        )

    assert svc.get_quiz(quiz["id"])["title"] == "Family"
