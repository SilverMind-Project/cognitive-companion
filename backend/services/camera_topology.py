"""Camera topology: maps raw person-ID movement directions to semantic room transitions.

Each camera sensor can declare a ``movement_map`` in its ``config_json`` that
translates the direction strings returned by the person-identification-service
("left-to-right", "right-to-left", "towards-camera", "away-from-camera",
"stationary") into semantically meaningful room transitions.

Example ``config_json`` for a doorway camera at the kitchen entrance::

    {
        "movement_map": {
            "left-to-right": {
                "semantic": "entering",
                "from_room_id": 2,
                "from_room_name": "Hallway",
                "to_room_id": 1,
                "to_room_name": "Kitchen"
            },
            "right-to-left": {
                "semantic": "exiting",
                "from_room_id": 1,
                "from_room_name": "Kitchen",
                "to_room_id": 2,
                "to_room_name": "Hallway"
            },
            "towards-camera": {
                "semantic": "approaching_exit",
                "from_room_id": 1,
                "from_room_name": "Kitchen",
                "to_room_id": null,
                "to_room_name": null
            },
            "away-from-camera": {
                "semantic": "entering_depth",
                "from_room_id": null,
                "from_room_name": null,
                "to_room_id": 1,
                "to_room_name": "Kitchen"
            }
        }
    }

Design
------
All functions in this module are pure (no I/O, no side effects) so they can
be tested without any database or service stubs.  The caller supplies the
sensor ``config_json`` dict; this module only interprets it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

# ---------------------------------------------------------------------------
# Semantic direction constants
# ---------------------------------------------------------------------------

SEMANTIC_ENTERING: Final[str] = "entering"
SEMANTIC_EXITING: Final[str] = "exiting"
SEMANTIC_APPROACHING_EXIT: Final[str] = "approaching_exit"
SEMANTIC_ENTERING_DEPTH: Final[str] = "entering_depth"
SEMANTIC_STATIONARY: Final[str] = "stationary"

_VALID_SEMANTICS: frozenset[str] = frozenset(
    {
        SEMANTIC_ENTERING,
        SEMANTIC_EXITING,
        SEMANTIC_APPROACHING_EXIT,
        SEMANTIC_ENTERING_DEPTH,
        SEMANTIC_STATIONARY,
    }
)

# Raw direction strings produced by the person-identification-service.
_STATIONARY_DIRECTION: Final[str] = "stationary"


# ---------------------------------------------------------------------------
# Data transfer object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoomTransition:
    """A semantic room-transition event derived from a raw movement direction.

    Attributes:
        person_id: Identifier of the detected person.
        person_name: Display name of the detected person.
        sensor_id: Sensor that produced the detection.
        direction_raw: The raw direction string from the person-ID service.
        semantic: One of the ``SEMANTIC_*`` constants defined above.
        from_room_id: Database ID of the origin room, or None when unknown.
        from_room_name: Display name of the origin room, or None when unknown.
        to_room_id: Database ID of the destination room, or None when unknown.
        to_room_name: Display name of the destination room, or None when unknown.
        confidence: Detection confidence score carried over from the face result.
    """

    person_id: str
    person_name: str
    sensor_id: str
    direction_raw: str
    semantic: str
    from_room_id: int | None
    from_room_name: str | None
    to_room_id: int | None
    to_room_name: str | None
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for pipeline_data."""
        return {
            "person_id": self.person_id,
            "person_name": self.person_name,
            "sensor_id": self.sensor_id,
            "direction_raw": self.direction_raw,
            "semantic": self.semantic,
            "from_room_id": self.from_room_id,
            "from_room_name": self.from_room_name,
            "to_room_id": self.to_room_id,
            "to_room_name": self.to_room_name,
            "confidence": self.confidence,
        }


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------


def infer_room_transition(
    *,
    person_id: str,
    person_name: str,
    sensor_id: str,
    direction_raw: str | None,
    confidence: float,
    sensor_config: dict[str, Any] | None,
) -> RoomTransition | None:
    """Map a raw person-ID direction to a semantic :class:`RoomTransition`.

    Returns ``None`` when:

    * ``direction_raw`` is absent or ``"stationary"``.
    * The sensor has no ``movement_map`` in its ``config_json``.
    * The direction is not listed in the map.
    * The mapped semantic value is not one of the recognised constants.

    Args:
        person_id: Identifier of the detected person.
        person_name: Display name of the detected person.
        sensor_id: Camera sensor that produced the detection.
        direction_raw: Raw direction string from the person-ID service.
        confidence: Face detection confidence score.
        sensor_config: Contents of ``Sensor.config_json``, or None.

    Returns:
        A :class:`RoomTransition` on success, or None.
    """
    if not direction_raw or direction_raw == _STATIONARY_DIRECTION:
        return None
    if not sensor_config:
        return None

    movement_map_raw = sensor_config.get("movement_map") or {}
    if not movement_map_raw:
        return None

    from backend.schemas.sensor_config import validate_movement_map

    parsed = validate_movement_map(movement_map_raw)
    if parsed is None:
        return None

    # Look up the mapping for this direction using the alias.
    entry = None
    for field_name, field_info in type(parsed).model_fields.items():
        if field_info.alias == direction_raw:
            entry = getattr(parsed, field_name)
            break

    if entry is None:
        return None

    return RoomTransition(
        person_id=person_id,
        person_name=person_name,
        sensor_id=sensor_id,
        direction_raw=direction_raw,
        semantic=entry.semantic,
        from_room_id=entry.from_room_id,
        from_room_name=entry.from_room_name,
        to_room_id=entry.to_room_id,
        to_room_name=entry.to_room_name,
        confidence=confidence,
    )
