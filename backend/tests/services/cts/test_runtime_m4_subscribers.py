"""CTSRuntime camera->room resolution tests.

M38 Part D removed the dormant reCamera-observation subscriber class (and
this file's lifecycle tests for it, which this module used to be named for):
reCamera identification now writes through
``backend.services.person_location.face_sighting_ingest.FaceSightingIngest``
instead, wired directly into ``PersonTrackingService`` (not CTSRuntime).
"""

from __future__ import annotations


def test_load_camera_room_id_map_resolves_room_id_and_name_fallback():
    """Cameras contribute via room_id OR a room_name that resolves to a room."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from backend.models.cts_camera import CtsCamera
    from backend.models.room import Room
    from backend.services.cts.runtime import _load_camera_room_id_map

    rooms = [SimpleNamespace(id=5, name="kitchen")]
    cameras = [
        SimpleNamespace(id="cam-id", room_id=9, room_name="ignored"),  # room_id wins
        SimpleNamespace(id="cam-name", room_id=None, room_name="kitchen"),  # name fallback
        SimpleNamespace(id="cam-orphan", room_id=None, room_name="garage"),  # unresolved
    ]

    def _query(model):
        q = MagicMock()
        if model is Room:
            q.all.return_value = rooms
        elif model is CtsCamera:
            q.filter.return_value.all.return_value = cameras
        return q

    db = MagicMock()
    db.query.side_effect = _query

    result = _load_camera_room_id_map(lambda: db)
    assert result == {"cam-id": 9, "cam-name": 5}
