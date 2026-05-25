"""Shared test factories for creating valid model instances.

Each factory returns a model instance (not persisted) with sensible
defaults so tests can focus on the fields that matter for the scenario.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.models.person import HouseholdMember
from backend.models.room import Room
from backend.models.sensor import Sensor


def make_room(name: str = "Test Room", **kwargs) -> Room:
    """Create a Room with sensible defaults."""
    defaults: dict = {
        "id": kwargs.pop("id", None) or _next_id(Room),
        "name": name,
        "created_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    return Room(**defaults)


def make_sensor(**kwargs) -> Sensor:
    """Create a Sensor with sensible defaults."""
    defaults: dict = {
        "id": kwargs.pop("id", None) or f"sensor-{_next_id(Sensor)}",
        "name": kwargs.pop("name", "Test Sensor"),
        "sensor_type": "camera",
        "source": "local",
        "enabled": True,
        "created_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    return Sensor(**defaults)


def make_household_member(
    person_id: str = "test-person", name: str = "Test Person", **kwargs
) -> HouseholdMember:
    """Create a HouseholdMember with sensible defaults."""
    defaults: dict = {
        "id": person_id,
        "name": name,
        "is_active": True,
        "is_guest": False,
        "created_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    return HouseholdMember(**defaults)


# -- helpers ---------------------------------------------------------------

_id_counters: dict[type, int] = {}


def _next_id(model_class: type) -> int:
    _id_counters[model_class] = _id_counters.get(model_class, 0) + 1
    return _id_counters[model_class]
