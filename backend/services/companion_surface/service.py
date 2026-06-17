"""Companion surface registry service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.exceptions import NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.models.companion_surface import CompanionSurface

logger = get_logger(__name__)

VALID_SURFACE_TYPES = frozenset({"fixed", "movable"})
VALID_ROOM_SOURCES = frozenset({"caregiver", "cts_inferred"})
VALID_KINDS = frozenset({"tablet", "speaker", "display"})


@dataclass(frozen=True)
class SurfaceView:
    id: str
    name: str
    surface_type: str
    room_id: int | None
    room_source: str
    kind: str
    is_enabled: bool
    last_seen_at: datetime | None
    room_mismatch: bool
    created_at: datetime
    updated_at: datetime


def _to_view(surface: CompanionSurface) -> SurfaceView:
    return SurfaceView(
        id=surface.id,
        name=surface.name,
        surface_type=surface.surface_type,
        room_id=surface.room_id,
        room_source=surface.room_source,
        kind=surface.kind,
        is_enabled=surface.is_enabled,
        last_seen_at=surface.last_seen_at,
        room_mismatch=surface.room_mismatch,
        created_at=surface.created_at,
        updated_at=surface.updated_at,
    )


class CompanionSurfaceService:
    """CRUD and CTS room cross-checks for companion surfaces."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        person_location_service: Any = None,
        time_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._db_factory = db_factory
        self._person_location_service = person_location_service
        self._time_fn = time_fn or (lambda: datetime.now(UTC))

    def set_person_location_service(self, person_location_service: Any) -> None:
        self._person_location_service = person_location_service

    def list_surfaces(self, *, limit: int = 50, offset: int = 0) -> tuple[list[SurfaceView], int]:
        db = self._db_factory()
        try:
            total = db.scalar(select(func.count()).select_from(CompanionSurface)) or 0
            stmt = (
                select(CompanionSurface)
                .order_by(CompanionSurface.name, CompanionSurface.id)
                .offset(offset)
                .limit(limit)
            )
            items = [_to_view(row) for row in db.execute(stmt).scalars().all()]
            return items, int(total)
        finally:
            db.close()

    def get_surface(self, surface_id: str) -> SurfaceView | None:
        db = self._db_factory()
        try:
            surface = db.get(CompanionSurface, surface_id)
            return _to_view(surface) if surface is not None else None
        finally:
            db.close()

    def upsert_surface(
        self,
        *,
        surface_id: str,
        name: str,
        surface_type: str,
        kind: str,
        room_id: int | None,
        is_enabled: bool = True,
    ) -> SurfaceView:
        self._validate(surface_type=surface_type, kind=kind)
        db = self._db_factory()
        try:
            surface = db.get(CompanionSurface, surface_id)
            if surface is None:
                surface = CompanionSurface(id=surface_id)
                db.add(surface)
            surface.name = name
            surface.surface_type = surface_type
            surface.kind = kind
            surface.room_id = room_id
            surface.room_source = "caregiver"
            surface.room_mismatch = False
            surface.is_enabled = is_enabled
            db.commit()
            db.refresh(surface)
            return _to_view(surface)
        finally:
            db.close()

    def update_surface(
        self,
        surface_id: str,
        *,
        name: str | None = None,
        surface_type: str | None = None,
        kind: str | None = None,
        room_id: int | None = None,
        room_id_set: bool = False,
        is_enabled: bool | None = None,
    ) -> SurfaceView:
        if surface_type is not None:
            self._validate(surface_type=surface_type, kind=kind)
        elif kind is not None:
            self._validate(surface_type="fixed", kind=kind)

        db = self._db_factory()
        try:
            surface = db.get(CompanionSurface, surface_id)
            if surface is None:
                raise NotFoundError("Companion surface", surface_id)
            if name is not None:
                surface.name = name
            if surface_type is not None:
                surface.surface_type = surface_type
            if kind is not None:
                surface.kind = kind
            if room_id_set:
                surface.room_id = room_id
                surface.room_source = "caregiver"
                surface.room_mismatch = False
            if is_enabled is not None:
                surface.is_enabled = is_enabled
            db.commit()
            db.refresh(surface)
            return _to_view(surface)
        finally:
            db.close()

    def surfaces_in_room(self, room_id: int) -> list[SurfaceView]:
        db = self._db_factory()
        try:
            stmt = (
                select(CompanionSurface)
                .where(
                    CompanionSurface.room_id == room_id,
                    CompanionSurface.is_enabled.is_(True),
                )
                .order_by(CompanionSurface.name, CompanionSurface.id)
            )
            return [_to_view(row) for row in db.execute(stmt).scalars().all()]
        finally:
            db.close()

    def record_heartbeat(self, surface_id: str, *, reported_room_id: int | None) -> None:
        now = self._now()
        db = self._db_factory()
        try:
            surface = db.get(CompanionSurface, surface_id)
            if surface is None:
                raise NotFoundError("Companion surface", surface_id)
            surface.last_seen_at = now
            if (
                reported_room_id is not None
                and surface.surface_type == "movable"
                and surface.room_source == "caregiver"
                and surface.room_id is not None
                and surface.room_id != reported_room_id
            ):
                surface.room_mismatch = True
                logger.warning(
                    "surface_room_mismatch",
                    surface_id=surface_id,
                    caregiver_room_id=surface.room_id,
                    reported_room_id=reported_room_id,
                )
            db.commit()
        finally:
            db.close()

    async def cross_check_room(self, surface_id: str, person_id: str) -> None:
        person_location = self._person_location_service
        if person_location is None:
            logger.info("surface_room_cross_check_skipped", surface_id=surface_id, reason="no_location_service")
            return

        location = await person_location.where_is(person_id)
        if location is None or location.room_id is None:
            logger.info("surface_room_cross_check_skipped", surface_id=surface_id, reason="no_location")
            return

        db = self._db_factory()
        try:
            surface = db.get(CompanionSurface, surface_id)
            if surface is None:
                raise NotFoundError("Companion surface", surface_id)
            if surface.surface_type != "movable":
                return
            if surface.room_source == "caregiver" and surface.room_id is not None:
                if surface.room_id != location.room_id:
                    surface.room_mismatch = True
                    logger.warning(
                        "surface_room_mismatch",
                        surface_id=surface_id,
                        caregiver_room_id=surface.room_id,
                        inferred_room_id=location.room_id,
                        person_id=person_id,
                    )
                else:
                    surface.room_mismatch = False
            else:
                surface.room_id = location.room_id
                surface.room_source = "cts_inferred"
                surface.room_mismatch = False
            db.commit()
        finally:
            db.close()

    def _now(self) -> datetime:
        now = self._time_fn()
        if now.tzinfo is None:
            raise ValueError("CompanionSurfaceService time_fn must return timezone-aware datetimes")
        return now

    def _validate(self, *, surface_type: str, kind: str | None) -> None:
        if surface_type not in VALID_SURFACE_TYPES:
            raise ValidationError(f"surface_type must be one of {sorted(VALID_SURFACE_TYPES)}")
        if kind is not None and kind not in VALID_KINDS:
            raise ValidationError(f"kind must be one of {sorted(VALID_KINDS)}")
