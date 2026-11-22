"""Service-layer tests for InfoCardService."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.services.knowledge.image_pipeline import RenderedVariant
from backend.services.knowledge.info_card_service import InfoCardService
from backend.services.knowledge.layout_registry import LayoutRegistry


@pytest.fixture
def layout_registry() -> LayoutRegistry:
    return LayoutRegistry.load("config/knowledge_layouts.yaml")


@pytest.fixture
def minio_client() -> Mock:
    minio = Mock()
    minio.generate_presigned_url.side_effect = lambda obj: f"http://minio.test/{obj}"
    minio.async_upload_bytes = AsyncMock()
    return minio


@pytest.fixture
def image_pipeline() -> Mock:
    pipeline = Mock()
    pipeline.validate_upload.return_value = (400, 300)
    pipeline.render_variants = AsyncMock(
        return_value={
            "pwa": RenderedVariant(
                object_name="info_cards/1/slot0__pwa.webp",
                width=400,
                height=300,
                format="webp",
                size_bytes=1024,
                generated_at="2026-11-22T00:00:00+00:00",
            )
        }
    )
    pipeline.purge_prefix = AsyncMock()
    return pipeline


@pytest.fixture
def info_card_service(
    db_factory, minio_client: Mock, image_pipeline: Mock, layout_registry: LayoutRegistry
) -> InfoCardService:
    return InfoCardService(
        db_factory=db_factory,
        minio_client=minio_client,
        image_pipeline=image_pipeline,
        layout_registry=layout_registry,
    )


def test_create_get_list_update_info_card(info_card_service: InfoCardService) -> None:
    created = info_card_service.create_card(
        title="Morning Hydration",
        body_text="Drink a full glass of water after waking up.",
        layout_id="text_only",
        voice_instruction="Read warmly.",
        tags=["morning", "health"],
    )
    card_id = created["id"]
    assert created["status"] == "draft"
    assert created["version"] == 1
    assert created["tags"] == ["morning", "health"]

    fetched = info_card_service.get_card(card_id)
    assert fetched["title"] == "Morning Hydration"
    assert fetched["voice_instruction"] == "Read warmly."

    listed = info_card_service.list_cards(status="draft", tag="morning")
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == card_id
    assert listed["items"][0]["slot_count"] == 0

    # Approve and verify content update bumps version
    approved = info_card_service.approve_card(card_id, approved_by="Caregiver Admin")
    assert approved["status"] == "approved"
    assert approved["version"] == 2
    assert approved["approved_by"] == "Caregiver Admin"

    updated = info_card_service.update_card(
        card_id, updates={"body_text": "Drink a warm glass of water after waking up."}
    )
    assert updated["version"] == 3
    assert updated["body_text"] == "Drink a warm glass of water after waking up."


async def test_approve_info_card_enforces_min_images(
    info_card_service: InfoCardService,
) -> None:
    card = info_card_service.create_card(
        title="Family Photo",
        body_text="Here is Priya in Boston.",
        layout_id="single_hero",
    )
    card_id = card["id"]

    with pytest.raises(ConflictError):
        info_card_service.approve_card(card_id, approved_by="Caregiver")

    slot = await info_card_service.set_slot(
        card_id,
        0,
        file_bytes=b"fake-image-bytes",
        content_type="image/jpeg",
        source_image_id=None,
        alt_text="Priya smiling",
    )
    assert slot["slot_index"] == 0
    assert (
        slot["variants"]["pwa"]["presigned_url"] == "http://minio.test/info_cards/1/slot0__pwa.webp"
    )

    patched = info_card_service.patch_slot(card_id, 0, alt_text="Priya in Boston")
    assert patched["alt_text"] == "Priya in Boston"

    approved = info_card_service.approve_card(card_id, approved_by="Caregiver")
    assert approved["status"] == "approved"


async def test_archive_restore_delete_info_card_purges_minio(
    info_card_service: InfoCardService, image_pipeline: Mock
) -> None:
    card = info_card_service.create_card(
        title="Archivable Card",
        body_text="Temporary note.",
        layout_id="text_only",
    )
    card_id = card["id"]

    assert info_card_service.archive_card(card_id) == {"status": "archived"}
    assert info_card_service.get_card(card_id)["status"] == "archived"

    assert info_card_service.restore_card(card_id) == {"status": "restored"}
    assert info_card_service.get_card(card_id)["status"] == "draft"

    await info_card_service.delete_card(card_id)
    image_pipeline.purge_prefix.assert_awaited_once_with(f"info_cards/{card_id}/")

    with pytest.raises(NotFoundError):
        info_card_service.get_card(card_id)


def test_create_info_card_rejects_invalid_layout(
    info_card_service: InfoCardService,
) -> None:
    with pytest.raises(ValidationError):
        info_card_service.create_card(
            title="Bad Layout",
            body_text="Quiz layout on info card",
            layout_id="quiz_with_optional_image",
        )
