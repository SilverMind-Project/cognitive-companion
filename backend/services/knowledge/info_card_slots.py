"""Image slots on info cards: binding, upload, variant rendering, and cleanup.

Part of :class:`~backend.services.knowledge.info_card_service.InfoCardService`, split out by
responsibility; it shares that service's injected session factory, MinIO client, image
pipeline, and layout validation.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.exceptions import NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.models.knowledge import InfoCard, InfoCardImageSlot, KnowledgeDocumentImage
from backend.services.knowledge.image_pipeline import ImagePipeline, variants_as_json
from backend.services.knowledge.layout_registry import LayoutSpec
from backend.services.knowledge.references import owned_object_names

# Logged under the info card service's logger so existing log queries keep matching.
logger = get_logger("backend.services.knowledge.info_card_service")


def slot_prefix(card_id: int, slot_index: int) -> str:
    """MinIO key prefix of one slot's objects (original and variants)."""
    # The trailing delimiter keeps slot 1's purge from matching slot 10's objects.
    return f"info_cards/{card_id}/slot{slot_index}__"


class InfoCardSlotsMixin:
    """Slot operations; slot objects live under ``info_cards/{card_id}/slot{index}__``."""

    _db_factory: Callable[[], Session]
    _minio: MinioClient | None
    _image_pipeline: ImagePipeline | None
    _validate_layout: Callable[[str], LayoutSpec]

    @staticmethod
    def _load_slots(db: Session, card_id: int) -> list[InfoCardImageSlot]:
        return list(
            db.execute(
                select(InfoCardImageSlot)
                .where(InfoCardImageSlot.info_card_id == card_id)
                .order_by(InfoCardImageSlot.slot_index.asc())
            ).scalars()
        )

    async def _rerender_slots(self, card_id: int, layout: LayoutSpec) -> None:
        """Re-render every slot's variants for ``layout`` and drop variants it no longer uses.

        Best-effort like any variant render: a slot whose render fails keeps its old variants
        and is logged, and delivery falls back to the slot's original image.
        """
        if self._image_pipeline is None:
            return
        db: Session = self._db_factory()
        try:
            snapshot = [
                (slot.slot_index, slot.original_object_name, dict(slot.variants or {}))
                for slot in self._load_slots(db, card_id)
            ]
        finally:
            db.close()

        rendered: dict[int, dict[str, Any]] = {}
        stale: set[str] = set()
        owner_prefix = f"info_cards/{card_id}/"
        for slot_index, original, old_variants in snapshot:
            if not original or slot_index >= len(layout.image_slots):
                continue
            try:
                variants = await self._image_pipeline.render_variants(
                    original_object_name=original,
                    layout_id=layout.id,
                    slot_id=layout.image_slots[slot_index].slot_id,
                    target_key_prefix=slot_prefix(card_id, slot_index).removesuffix("__"),
                )
            except Exception:  # noqa: BLE001 - variant rendering is best-effort
                logger.warning(
                    "info_card_slot_rerender_failed",
                    card_id=card_id,
                    slot_index=slot_index,
                    layout_id=layout.id,
                )
                continue
            new_json = variants_as_json(variants)
            rendered[slot_index] = new_json
            stale |= owned_object_names(
                {"variants": old_variants}, owner_prefix
            ) - owned_object_names({"variants": new_json}, owner_prefix)

        if not rendered:
            return
        db = self._db_factory()
        try:
            for slot in self._load_slots(db, card_id):
                if slot.slot_index in rendered:
                    slot.variants = rendered[slot.slot_index]
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        await self._image_pipeline.purge_objects(stale)

    async def set_slot(
        self,
        card_id: int,
        slot_index: int,
        *,
        file_bytes: bytes | None,
        content_type: str | None,
        source_image_id: int | None,
        alt_text: str,
    ) -> dict[str, Any]:
        db: Session = self._db_factory()
        try:
            card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
            if card is None:
                raise NotFoundError("InfoCard", card_id)

            layout = self._validate_layout(card.layout_id)
            if slot_index < 0 or slot_index >= len(layout.image_slots):
                raise ValidationError(f"Layout '{layout.id}' has no slot at index {slot_index}")

            original_object_name = ""
            if file_bytes is not None:
                ctype = content_type or "image/jpeg"
                if self._image_pipeline is not None:
                    self._image_pipeline.validate_upload(ctype, file_bytes)
                ext = ctype.split("/")[-1]
                if ext == "jpeg":
                    ext = "jpg"
                object_name = f"info_cards/{card_id}/slot{slot_index}__original.{ext}"
                if self._minio is not None:
                    await self._minio.async_upload_bytes(file_bytes, object_name, ctype)
                original_object_name = object_name
            elif source_image_id is not None:
                src = db.execute(
                    select(KnowledgeDocumentImage).where(
                        KnowledgeDocumentImage.id == source_image_id
                    )
                ).scalar_one_or_none()
                if src is None:
                    raise NotFoundError("Source image", source_image_id)
                original_object_name = src.minio_object_name

            slot = db.execute(
                select(InfoCardImageSlot).where(
                    InfoCardImageSlot.info_card_id == card_id,
                    InfoCardImageSlot.slot_index == slot_index,
                )
            ).scalar_one_or_none()

            if slot is None:
                slot = InfoCardImageSlot(
                    info_card_id=card_id,
                    slot_index=slot_index,
                    source_image_id=source_image_id,
                    original_object_name=original_object_name,
                    alt_text=alt_text,
                )
                db.add(slot)
            else:
                if original_object_name:
                    slot.original_object_name = original_object_name
                if source_image_id is not None:
                    slot.source_image_id = source_image_id
                slot.alt_text = alt_text or slot.alt_text

            db.commit()
            db.refresh(slot)

            if original_object_name and self._image_pipeline is not None:
                try:
                    variants = await self._image_pipeline.render_variants(
                        original_object_name=original_object_name,
                        layout_id=card.layout_id,
                        slot_id=layout.image_slots[slot_index].slot_id,
                        target_key_prefix=f"info_cards/{card_id}/slot{slot_index}",
                    )
                    slot.variants = variants_as_json(variants)
                    db.commit()
                    db.refresh(slot)
                except Exception:  # noqa: BLE001 - variant rendering is best-effort
                    logger.warning(
                        "info_card_slot_variant_render_failed",
                        card_id=card_id,
                        slot_index=slot_index,
                    )

            return self._slot_out(slot)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def patch_slot(self, card_id: int, slot_index: int, *, alt_text: str | None) -> dict[str, Any]:
        db: Session = self._db_factory()
        try:
            slot = db.execute(
                select(InfoCardImageSlot).where(
                    InfoCardImageSlot.info_card_id == card_id,
                    InfoCardImageSlot.slot_index == slot_index,
                )
            ).scalar_one_or_none()
            if slot is None:
                raise NotFoundError(f"Slot for info card {card_id}", slot_index)
            if alt_text is not None:
                slot.alt_text = alt_text
            db.commit()
            db.refresh(slot)
            return self._slot_out(slot)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def delete_slot(self, card_id: int, slot_index: int) -> None:
        db: Session = self._db_factory()
        try:
            slot = db.execute(
                select(InfoCardImageSlot).where(
                    InfoCardImageSlot.info_card_id == card_id,
                    InfoCardImageSlot.slot_index == slot_index,
                )
            ).scalar_one_or_none()
            if slot is None:
                raise NotFoundError(f"Slot for info card {card_id}", slot_index)
            db.delete(slot)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        if self._image_pipeline is not None:
            await self._image_pipeline.purge_prefix(slot_prefix(card_id, slot_index))

    def _slot_out(self, slot: InfoCardImageSlot) -> dict[str, Any]:
        variants: dict[str, Any] = {}
        for surface, v in (slot.variants or {}).items():
            entry = dict(v)
            object_name = v.get("object_name", "")
            if object_name and self._minio is not None:
                try:
                    entry["presigned_url"] = self._minio.generate_presigned_url(object_name)
                except Exception:  # noqa: BLE001 - optional presigned URL enrichment
                    entry["presigned_url"] = None
            else:
                entry["presigned_url"] = None
            variants[surface] = entry

        return {
            "id": slot.id,
            "info_card_id": slot.info_card_id,
            "slot_index": slot.slot_index,
            "source_image_id": slot.source_image_id,
            "original_object_name": slot.original_object_name,
            "alt_text": slot.alt_text,
            "variants": variants,
        }
