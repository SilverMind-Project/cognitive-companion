"""Medication schedule endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from backend.core.auth import AuthContext, require_permission
from backend.routers.dependencies import get_medication_schedule_service
from backend.schemas.medication import (
    MedicationEntryCreate,
    MedicationEntryOut,
    MedicationEntryUpdate,
    MedicationScheduleOut,
)
from backend.services.medication_schedule import MedicationScheduleService

router = APIRouter(prefix="/persons/{person_id}/medication-schedule", tags=["medication"])


@router.get("", response_model=MedicationScheduleOut)
def list_medication_schedule(
    person_id: str,
    svc: MedicationScheduleService = Depends(get_medication_schedule_service),
    _auth: AuthContext = Depends(require_permission("medication:read")),
) -> MedicationScheduleOut:
    items = [MedicationEntryOut.model_validate(entry) for entry in svc.list_entries(person_id)]
    return MedicationScheduleOut(items=items, total=len(items))


@router.post("", response_model=MedicationEntryOut, status_code=201)
def create_medication_entry(
    person_id: str,
    payload: MedicationEntryCreate,
    svc: MedicationScheduleService = Depends(get_medication_schedule_service),
    _auth: AuthContext = Depends(require_permission("medication:write")),
) -> MedicationEntryOut:
    return MedicationEntryOut.model_validate(
        svc.create_entry(
            person_id,
            label=payload.label,
            dose_time=payload.dose_time,
            days_of_week=payload.days_of_week,
        )
    )


@router.patch("/{entry_id}", response_model=MedicationEntryOut)
def update_medication_entry(
    person_id: str,
    entry_id: int,
    payload: MedicationEntryUpdate,
    svc: MedicationScheduleService = Depends(get_medication_schedule_service),
    _auth: AuthContext = Depends(require_permission("medication:write")),
) -> MedicationEntryOut:
    return MedicationEntryOut.model_validate(
        svc.update_entry(
            person_id,
            entry_id,
            label=payload.label,
            dose_time=payload.dose_time,
            days_of_week=payload.days_of_week,
        )
    )


@router.delete("/{entry_id}", status_code=204)
def delete_medication_entry(
    person_id: str,
    entry_id: int,
    svc: MedicationScheduleService = Depends(get_medication_schedule_service),
    _auth: AuthContext = Depends(require_permission("medication:write")),
) -> Response:
    svc.remove_entry(person_id, entry_id)
    return Response(status_code=204)
