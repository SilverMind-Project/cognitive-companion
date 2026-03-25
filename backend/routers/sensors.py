from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.exceptions import ConflictError, NotFoundError
from backend.models.sensor import Sensor
from backend.schemas.sensor import SensorCreate, SensorOut, SensorUpdate

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.get("", response_model=list[SensorOut])
def list_sensors(
    room_id: int | None = Query(None),
    sensor_type: str | None = Query(None),
    source: str | None = Query(None),
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("sensors:read")),
):
    q = db.query(Sensor)
    if room_id is not None:
        q = q.filter(Sensor.room_id == room_id)
    if sensor_type:
        q = q.filter(Sensor.sensor_type == sensor_type)
    if source:
        q = q.filter(Sensor.source == source)
    return q.order_by(Sensor.name).all()


@router.post("", response_model=SensorOut, status_code=201)
def create_sensor(
    payload: SensorCreate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("sensors:write")),
):
    existing = db.get(Sensor, payload.id)
    if existing:
        raise ConflictError(f"Sensor '{payload.id}' already exists")
    sensor = Sensor(**payload.model_dump())
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return sensor


@router.get("/{sensor_id}", response_model=SensorOut)
def get_sensor(
    sensor_id: str,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("sensors:read")),
):
    sensor = db.get(Sensor, sensor_id)
    if not sensor:
        raise NotFoundError("Sensor", sensor_id)
    return sensor


@router.put("/{sensor_id}", response_model=SensorOut)
def update_sensor(
    sensor_id: str,
    payload: SensorUpdate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("sensors:write")),
):
    sensor = db.get(Sensor, sensor_id)
    if not sensor:
        raise NotFoundError("Sensor", sensor_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(sensor, key, value)
    db.commit()
    db.refresh(sensor)
    return sensor


@router.delete("/{sensor_id}", status_code=204)
def delete_sensor(
    sensor_id: str,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("sensors:write")),
):
    sensor = db.get(Sensor, sensor_id)
    if not sensor:
        raise NotFoundError("Sensor", sensor_id)
    db.delete(sensor)
    db.commit()
