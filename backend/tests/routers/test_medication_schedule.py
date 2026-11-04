"""Router tests for medication schedules."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.models.person import HouseholdMember
from backend.routers import medication_schedule
from backend.routers.dependencies import get_medication_schedule_service
from backend.services.medication_schedule import MedicationScheduleService

URL = "/api/v1/persons/rose/medication-schedule"


@pytest.fixture
def client(db_factory, db_session) -> TestClient:
    db_session.add(HouseholdMember(id="rose", name="Rose"))
    db_session.commit()
    app = FastAPI()
    register_exception_handlers(app)
    svc = MedicationScheduleService(db_factory)
    app.include_router(medication_schedule.router, prefix="/api/v1")
    app.dependency_overrides[get_medication_schedule_service] = lambda: svc
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="admin", name="Admin", permissions=["admin"]
    )
    return TestClient(app, raise_server_exceptions=False)


def test_create_list_update_delete(client) -> None:
    created = client.post(URL, json={"label": "Morning tablets", "dose_time": "23:59"})
    assert created.status_code == 201
    body = created.json()
    assert body["dose_time"] == "23:59"
    assert body["days_of_week"] == [0, 1, 2, 3, 4, 5, 6]

    listing = client.get(URL).json()
    assert listing["total"] == 1

    updated = client.patch(f"{URL}/{body['id']}", json={"label": "Heart tablets"})
    assert updated.status_code == 200
    assert client.get(URL).json()["items"][0]["label"] == "Heart tablets"

    removed = client.delete(f"{URL}/{updated.json()['id']}")
    assert removed.status_code == 204
    assert client.get(URL).json()["total"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"label": "", "dose_time": "08:00"},
        {"label": "Tablets", "dose_time": "25:00"},
        {"label": "Tablets", "dose_time": "08:00+02:00"},
        {"label": "Tablets", "dose_time": "08:00", "days_of_week": []},
        {"label": "Tablets", "dose_time": "08:00", "days_of_week": [7]},
        {"label": "Tablets", "dose_time": "08:00", "extra": 1},
    ],
)
def test_bad_input_is_rejected(client, payload) -> None:
    assert client.post(URL, json=payload).status_code == 422


def test_unknown_person_is_404(client) -> None:
    assert client.get("/api/v1/persons/nobody/medication-schedule").status_code == 404


def test_unknown_entry_is_404(client) -> None:
    assert client.delete(f"{URL}/999").status_code == 404


def test_caregivers_can_read_and_write_the_schedule() -> None:
    auth = yaml.safe_load(Path("config/auth.yaml").read_text())
    caregiver = auth["permission_map"]["caregiver"]
    assert {"medication:read", "medication:write"} <= set(caregiver)
    assert (
        "POST /api/v1/persons/*/medication-schedule" in auth["permission_map"]["medication:write"]
    )
