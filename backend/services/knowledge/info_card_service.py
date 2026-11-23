"""Info card CRUD, approval/archive lifecycle, and image slot rendering."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.models.knowledge import (
    InfoCard,
    InfoCardDelivery,
    InfoCardImageSlot,
)
from backend.services.knowledge.image_pipeline import ImagePipeline
from backend.services.knowledge.info_card_slots import InfoCardSlotsMixin, slot_prefix
from backend.services.knowledge.layout_registry import LayoutRegistry, LayoutSpec
from backend.services.knowledge.references import rule_ids_referencing

logger = get_logger(__name__)

_VALID_CARD_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"caregiver_review", "approved", "archived"},
    "caregiver_review": {"approved", "draft", "archived"},
    "approved": {"archived", "draft"},
    "archived": {"draft"},
}

_CONTENT_FIELDS: frozenset[str] = frozenset(
    {"title", "body_text", "voice_instruction", "layout_id"}
)


class InfoCardService(InfoCardSlotsMixin):
    """Business logic for info cards; slot image operations live in :class:`InfoCardSlotsMixin`."""

    def __init__(
        self,
        db_factory: Callable[[], Session],
        minio_client: MinioClient | None,
        image_pipeline: ImagePipeline | None,
        layout_registry: LayoutRegistry,
    ) -> None:
        self._db_factory = db_factory
        self._minio = minio_client
        self._image_pipeline = image_pipeline
        self._layouts = layout_registry

    def _validate_layout(self, layout_id: str) -> Any:
        layout = self._layouts.get(layout_id)
        if layout is None or "info_card" not in layout.applies_to:
            raise ValidationError(f"Layout '{layout_id}' does not apply to info_card")
        return layout

    def create_card(
        self,
        *,
        title: str,
        body_text: str,
        layout_id: str = "text_only",
        document_id: int | None = None,
        voice_instruction: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        self._validate_layout(layout_id)
        db: Session = self._db_factory()
        try:
            card = InfoCard(
                document_id=document_id,
                layout_id=layout_id,
                title=title,
                body_text=body_text,
                voice_instruction=voice_instruction,
                tags=tags or [],
                status="draft",
                version=1,
            )
            db.add(card)
            db.commit()
            db.refresh(card)
            return self._card_out(card, [])
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def list_cards(
        self,
        *,
        status: str | None = None,
        tags: list[str] | None = None,
        document_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        db: Session = self._db_factory()
        try:
            stmt = select(InfoCard)
            count_stmt = select(func.count(InfoCard.id))
            if status:
                stmt = stmt.where(InfoCard.status == status)
                count_stmt = count_stmt.where(InfoCard.status == status)
            if tags:
                # Any selected tag matches (array overlap), the same as the knowledge
                # query step's tag filter.
                stmt = stmt.where(InfoCard.tags.overlap(tags))
                count_stmt = count_stmt.where(InfoCard.tags.overlap(tags))
            if document_id is not None:
                stmt = stmt.where(InfoCard.document_id == document_id)
                count_stmt = count_stmt.where(InfoCard.document_id == document_id)

            total = db.execute(count_stmt).scalar() or 0
            cards = (
                db.execute(stmt.order_by(InfoCard.created_at.desc()).offset(offset).limit(limit))
                .scalars()
                .all()
            )

            card_ids = [c.id for c in cards]
            slot_counts: dict[int, int] = {}
            if card_ids:
                rows = db.execute(
                    select(
                        InfoCardImageSlot.info_card_id,
                        func.count(InfoCardImageSlot.id).label("cnt"),
                    )
                    .where(InfoCardImageSlot.info_card_id.in_(card_ids))
                    .group_by(InfoCardImageSlot.info_card_id)
                ).all()
                slot_counts = {row.info_card_id: row.cnt for row in rows}

            return {
                "items": [
                    {
                        "id": c.id,
                        "document_id": c.document_id,
                        "layout_id": c.layout_id,
                        "title": c.title,
                        "tags": c.tags or [],
                        "status": c.status,
                        "version": c.version,
                        "approved_by": c.approved_by,
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                        "slot_count": slot_counts.get(c.id, 0),
                    }
                    for c in cards
                ],
                "total": total,
            }
        finally:
            db.close()

    def get_card(self, card_id: int) -> dict[str, Any]:
        db: Session = self._db_factory()
        try:
            card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
            if card is None:
                raise NotFoundError("InfoCard", card_id)
            slots = (
                db.execute(
                    select(InfoCardImageSlot)
                    .where(InfoCardImageSlot.info_card_id == card_id)
                    .order_by(InfoCardImageSlot.slot_index.asc())
                )
                .scalars()
                .all()
            )
            return self._card_out(card, list(slots))
        finally:
            db.close()

    async def update_card(self, card_id: int, *, updates: dict[str, Any]) -> dict[str, Any]:
        """Apply field updates; a layout change also reshapes the card's image slots.

        Changing the layout drops slots the new layout has no position for and re-renders the
        remaining slots for the new layout's surfaces. An approved card is never left unable to
        render: if the slots that fit the new layout fall short of its ``min_images``, the
        change is rejected (409) rather than silently unpublishing a card rules deliver.
        """
        new_layout: LayoutSpec | None = None
        if updates.get("layout_id") is not None:
            new_layout = self._validate_layout(updates["layout_id"])

        pruned_indexes: list[int] = []
        layout_changed = False
        db: Session = self._db_factory()
        try:
            card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
            if card is None:
                raise NotFoundError("InfoCard", card_id)

            layout_changed = new_layout is not None and new_layout.id != card.layout_id
            if new_layout is not None and layout_changed:
                slots = self._load_slots(db, card_id)
                capacity = len(new_layout.image_slots)
                kept = [slot for slot in slots if slot.slot_index < capacity]
                if card.status == "approved" and len(kept) < new_layout.min_images:
                    raise ConflictError(
                        f"Layout '{new_layout.id}' needs at least {new_layout.min_images} "
                        f"image(s), but this approved card has {len(kept)} that fit it. Add "
                        "images first, or move the card back to draft before changing layout."
                    )
                for slot in slots:
                    if slot.slot_index >= capacity:
                        pruned_indexes.append(slot.slot_index)
                        db.delete(slot)

            content_changed = any(
                field in updates
                and updates[field] is not None
                and getattr(card, field) != updates[field]
                for field in _CONTENT_FIELDS
            )
            for key, val in updates.items():
                if val is not None and hasattr(card, key):
                    setattr(card, key, val)

            if card.status == "approved" and content_changed:
                card.version += 1

            card.updated_at = datetime.now(UTC)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        if self._image_pipeline is not None:
            for slot_index in pruned_indexes:
                await self._image_pipeline.purge_prefix(slot_prefix(card_id, slot_index))
            if new_layout is not None and layout_changed:
                await self._rerender_slots(card_id, new_layout)
        return self.get_card(card_id)

    def approve_card(self, card_id: int, *, approved_by: str | None) -> dict[str, Any]:
        db: Session = self._db_factory()
        try:
            card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
            if card is None:
                raise NotFoundError("InfoCard", card_id)

            allowed = _VALID_CARD_TRANSITIONS.get(card.status, set())
            if "approved" not in allowed and card.status != "approved":
                raise ConflictError(
                    f"Cannot transition info card {card_id} from '{card.status}' to 'approved'"
                )

            layout = self._validate_layout(card.layout_id)
            slots = (
                db.execute(
                    select(InfoCardImageSlot)
                    .where(InfoCardImageSlot.info_card_id == card_id)
                    .order_by(InfoCardImageSlot.slot_index.asc())
                )
                .scalars()
                .all()
            )
            if len(slots) < layout.min_images:
                raise ConflictError(
                    f"Layout '{layout.id}' requires at least {layout.min_images} image(s), "
                    f"got {len(slots)}"
                )

            card.status = "approved"
            card.version += 1
            card.approved_at = datetime.now(UTC)
            card.approved_by = approved_by
            card.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(card)
            return self._card_out(card, list(slots))
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def archive_card(self, card_id: int) -> dict[str, str]:
        db: Session = self._db_factory()
        try:
            card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
            if card is None:
                raise NotFoundError("InfoCard", card_id)
            card.status = "archived"
            card.updated_at = datetime.now(UTC)
            db.commit()
            return {"status": "archived"}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def restore_card(self, card_id: int) -> dict[str, str]:
        db: Session = self._db_factory()
        try:
            card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
            if card is None:
                raise NotFoundError("InfoCard", card_id)
            card.status = "draft"
            card.updated_at = datetime.now(UTC)
            db.commit()
            return {"status": "restored"}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def delete_card(self, card_id: int) -> None:
        """Hard-delete a card that no rule uses and that was never delivered.

        Raises 409 when any rule step (enabled or disabled) references the card, or when
        delivery history exists (protected by an ``ON DELETE RESTRICT`` foreign key); the
        caregiver archives such a card instead. MinIO objects are purged only after commit.
        """
        db: Session = self._db_factory()
        try:
            card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
            if card is None:
                raise NotFoundError("InfoCard", card_id)
            rule_ids = rule_ids_referencing(
                db, step_type="info_card", config_key="info_card_id", resource_id=card_id
            )
            if rule_ids:
                raise ConflictError(
                    f"Info card {card_id} is used by rule(s) {rule_ids}; remove it from those "
                    "rules or archive the card instead."
                )
            db.delete(card)
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                deliveries = (
                    db.execute(
                        select(func.count(InfoCardDelivery.id)).where(
                            InfoCardDelivery.info_card_id == card_id
                        )
                    ).scalar()
                    or 0
                )
                raise ConflictError(
                    f"Info card {card_id} has {deliveries} delivery record(s) and cannot be "
                    "deleted; archive it instead."
                ) from exc
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        if self._image_pipeline is not None:
            await self._image_pipeline.purge_prefix(f"info_cards/{card_id}/")

    def _card_out(
        self, card: InfoCard, slots: list[InfoCardImageSlot] | None = None
    ) -> dict[str, Any]:
        resolved_slots = slots if slots is not None else list(card.image_slots or [])
        return {
            "id": card.id,
            "document_id": card.document_id,
            "layout_id": card.layout_id,
            "title": card.title,
            "body_text": card.body_text,
            "voice_instruction": card.voice_instruction or "",
            "tags": card.tags or [],
            "status": card.status,
            "version": card.version,
            "approved_by": card.approved_by,
            "approved_at": card.approved_at.isoformat() if card.approved_at else None,
            "created_at": card.created_at.isoformat() if card.created_at else None,
            "updated_at": card.updated_at.isoformat() if card.updated_at else None,
            "image_slots": [self._slot_out(s) for s in resolved_slots],
        }
