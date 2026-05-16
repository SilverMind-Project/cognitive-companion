from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.exceptions import ConflictError, NotFoundError
from backend.models.room import Room
from backend.schemas.room import RoomCreate, RoomOut, RoomUpdate
from backend.services.cts.room_rename import on_room_deleted, on_room_renamed

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomOut])
def list_rooms(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rooms:read")),
):
    return db.query(Room).order_by(Room.name).all()


@router.post("", response_model=RoomOut, status_code=201)
def create_room(
    payload: RoomCreate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rooms:write")),
):
    existing = db.query(Room).filter(Room.name == payload.name).first()
    if existing:
        raise ConflictError(f"Room '{payload.name}' already exists")
    room = Room(**payload.model_dump())
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@router.get("/{room_id}", response_model=RoomOut)
def get_room(
    room_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rooms:read")),
):
    room = db.get(Room, room_id)
    if not room:
        raise NotFoundError("Room", room_id)
    return room


@router.put("/{room_id}", response_model=RoomOut)
def update_room(
    room_id: int,
    payload: RoomUpdate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rooms:write")),
):
    room = db.get(Room, room_id)
    if not room:
        raise NotFoundError("Room", room_id)
    old_name = room.name
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(room, key, value)
    db.flush()
    if payload.name is not None and payload.name != old_name:
        on_room_renamed(db, room_id, payload.name)
    db.commit()
    db.refresh(room)
    return room


@router.delete("/{room_id}", status_code=204)
def delete_room(
    room_id: int,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("rooms:write")),
):
    room = db.get(Room, room_id)
    if not room:
        raise NotFoundError("Room", room_id)
    on_room_deleted(db, room_id)
    db.delete(room)
    db.commit()
