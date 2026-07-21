"""Unit tests for :class:`~backend.steps.builtin.person_identification.PersonIdentificationHandler`.

Tests cover:
* Early-exit when person_tracking service is absent.
* Sensor config lookup via db_factory (real in-memory DB).
* Correct forwarding of sensor_config to process_camera_event.
* room_transitions serialisation in result_data.
* target_person filter logic (passes / short-circuits).
* source_media_path annotation on detection dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.integrations.minio_client import MinioClient
from backend.models.sensor import Sensor
from backend.services.camera_topology import RoomTransition
from backend.services.person_tracking import CameraEventResult, PersonDetection
from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.person_identification import PersonIdentificationHandler

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeExecution:
    id: int = 1


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)


def _make_step(config: dict | None = None) -> _FakeStep:
    return _FakeStep(config_json=config or {})


def _make_trigger(
    sensor_id: str = "cam-kitchen",
    room_name: str = "Kitchen",
    media_paths: list[str] | None = None,
) -> TriggerContext:
    return TriggerContext(
        trigger_type="sensor_event",
        sensor_id=sensor_id,
        room_name=room_name,
        media_paths=media_paths or ["http://minio/frame0.jpg"],
    )


def _make_detection(
    person_id: str = "alice",
    name: str = "Alice",
    confidence: float = 0.95,
    direction: str | None = None,
    frame_index: int = 0,
) -> PersonDetection:
    return PersonDetection(
        person_id=person_id,
        name=name,
        confidence=confidence,
        bbox=[0, 0, 100, 100],
        direction=direction,
        frame_index=frame_index,
    )


def _make_transition(
    person_id: str = "alice",
    semantic: str = "entering",
    to_room_name: str = "Kitchen",
) -> RoomTransition:
    return RoomTransition(
        person_id=person_id,
        person_name="Alice",
        sensor_id="cam-kitchen",
        direction_raw="left-to-right",
        semantic=semantic,
        from_room_id=2,
        from_room_name="Hallway",
        to_room_id=1,
        to_room_name=to_room_name,
        confidence=0.95,
    )


def _make_services(
    db_factory=None,
    person_tracking=None,
    event_aggregator=None,
    minio_client=None,
) -> ServiceContainer:
    return ServiceContainer(
        db_factory=db_factory or MagicMock(return_value=MagicMock()),
        person_tracking=person_tracking,
        event_aggregator=event_aggregator,
        minio_client=minio_client,
    )


def _make_person_tracking(
    detections: list[PersonDetection] | None = None,
    transitions: list[RoomTransition] | None = None,
) -> AsyncMock:
    """Return an AsyncMock person_tracking service returning the given result."""
    svc = AsyncMock()
    svc.process_camera_event = AsyncMock(
        return_value=CameraEventResult(
            detections=detections or [],
            room_transitions=transitions or [],
        )
    )
    return svc


# ---------------------------------------------------------------------------
# Handler instance
# ---------------------------------------------------------------------------

_HANDLER = PersonIdentificationHandler()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestMetadata:
    def test_type_name(self):
        assert _HANDLER.metadata().type_name == "person_identification"

    def test_category(self):
        assert _HANDLER.metadata().category == "perception"

    def test_default_config_has_expected_keys(self):
        keys = _HANDLER.metadata().default_config.keys()
        assert "target_persons" in keys
        assert "min_confidence" in keys


# ---------------------------------------------------------------------------
# Early exit when person_tracking is absent
# ---------------------------------------------------------------------------


class TestNoPersonTrackingService:
    async def test_returns_empty_result(self):
        services = _make_services()
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )
        assert result.success is True
        assert result.data["person_detections"] == []
        assert result.data["room_transitions"] == []

    async def test_continues_pipeline(self):
        services = _make_services()
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )
        assert result.should_continue is True


# ---------------------------------------------------------------------------
# Sensor config lookup
# ---------------------------------------------------------------------------


class TestSensorConfigLookup:
    async def test_loads_sensor_config_from_db(self, db_session, db_factory):
        """sensor.config_json must be fetched and forwarded to process_camera_event."""
        movement_map = {"left-to-right": {"semantic": "entering"}}
        sensor = Sensor(
            id="cam-kitchen",
            name="Kitchen Cam",
            sensor_type="camera",
            config_json={"movement_map": movement_map},
        )
        db_session.add(sensor)
        db_session.commit()

        person_tracking = _make_person_tracking()
        services = _make_services(db_factory=db_factory, person_tracking=person_tracking)

        await _HANDLER.execute(_make_step(), _FakeExecution(), {}, _make_trigger(), services)

        call_kwargs = person_tracking.process_camera_event.call_args.kwargs
        assert call_kwargs["sensor_config"] == {"movement_map": movement_map}

    async def test_passes_none_config_when_sensor_not_in_db(self, db_session, db_factory):
        """No sensor row → sensor_config=None is forwarded gracefully."""
        person_tracking = _make_person_tracking()
        services = _make_services(db_factory=db_factory, person_tracking=person_tracking)

        await _HANDLER.execute(_make_step(), _FakeExecution(), {}, _make_trigger(), services)

        call_kwargs = person_tracking.process_camera_event.call_args.kwargs
        assert call_kwargs["sensor_config"] is None

    async def test_passes_none_config_when_sensor_id_is_none(self):
        """trigger.sensor_id=None must not crash and should forward None."""
        person_tracking = _make_person_tracking()
        db_mock = MagicMock()
        services = _make_services(db_factory=lambda: db_mock, person_tracking=person_tracking)
        trigger = _make_trigger(sensor_id=None)

        await _HANDLER.execute(_make_step(), _FakeExecution(), {}, trigger, services)

        call_kwargs = person_tracking.process_camera_event.call_args.kwargs
        assert call_kwargs["sensor_config"] is None
        # DB must NOT have been touched when sensor_id is None.
        db_mock.execute.assert_not_called()


# ---------------------------------------------------------------------------
# result_data structure
# ---------------------------------------------------------------------------


class TestResultData:
    async def test_person_detections_in_result(self):
        det = _make_detection()
        person_tracking = _make_person_tracking(detections=[det])
        services = _make_services(person_tracking=person_tracking)

        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )

        assert len(result.data["person_detections"]) == 1
        assert result.data["person_detections"][0]["person_id"] == "alice"

    async def test_room_transitions_in_result(self):
        transition = _make_transition()
        person_tracking = _make_person_tracking(
            detections=[_make_detection()],
            transitions=[transition],
        )
        services = _make_services(person_tracking=person_tracking)

        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )

        assert len(result.data["room_transitions"]) == 1
        rt = result.data["room_transitions"][0]
        assert rt["person_id"] == "alice"
        assert rt["semantic"] == "entering"
        assert rt["to_room_name"] == "Kitchen"

    async def test_empty_transitions_when_no_topology(self):
        person_tracking = _make_person_tracking(detections=[_make_detection()])
        services = _make_services(person_tracking=person_tracking)

        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )

        assert result.data["room_transitions"] == []

    async def test_write_movements_maps_transition_fields(self):
        """Regression: the write-movements branch reads the camera_topology
        RoomTransition's ``.semantic`` (not the nonexistent ``.direction_semantic``)
        and coerces int room ids to str. Before the fix this branch raised
        AttributeError at runtime (it was reachable but untested).

        DL-M02: the write now goes through ``scene_intel.persist_movements``
        (the single write seam) instead of the raw semantic-memory client;
        ``semantic_memory_client`` stays as the gating check for whether
        semantic memory is configured at all."""
        transition = _make_transition(semantic="entering")
        person_tracking = _make_person_tracking(
            detections=[_make_detection()],
            transitions=[transition],
        )
        scene_intel = MagicMock()
        scene_intel.persist_movements = AsyncMock(return_value=[42])
        services = _make_services(person_tracking=person_tracking)
        services.semantic_memory_client = MagicMock()
        services.scene_intel = scene_intel

        result = await _HANDLER.execute(
            _make_step({"write_movements_to_memory": True}),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )

        assert result.data["semantic_memory_movement_ids"] == [42]
        scene_intel.persist_movements.assert_awaited_once()
        transitions = scene_intel.persist_movements.await_args.args[0]
        assert transitions[0].direction_semantic == "entering"
        assert transitions[0].from_room_id == "2"
        assert transitions[0].to_room_id == "1"

    async def test_write_movements_skipped_when_semantic_memory_unconfigured(self):
        """No semantic_memory_client -> movements block does not run at all,
        matching current behavior when semantic memory is unconfigured."""
        transition = _make_transition(semantic="entering")
        person_tracking = _make_person_tracking(
            detections=[_make_detection()],
            transitions=[transition],
        )
        scene_intel = MagicMock()
        scene_intel.persist_movements = AsyncMock(return_value=[42])
        services = _make_services(person_tracking=person_tracking)
        services.scene_intel = scene_intel
        # services.semantic_memory_client left at its ServiceContainer default (None).

        result = await _HANDLER.execute(
            _make_step({"write_movements_to_memory": True}),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )

        assert "semantic_memory_movement_ids" not in result.data
        scene_intel.persist_movements.assert_not_awaited()

    async def test_source_media_path_annotated_on_detections(self):
        det = _make_detection(frame_index=0)
        person_tracking = _make_person_tracking(detections=[det])
        trigger = _make_trigger(media_paths=["http://minio/frame0.jpg", "http://minio/frame1.jpg"])
        services = _make_services(person_tracking=person_tracking)

        result = await _HANDLER.execute(_make_step(), _FakeExecution(), {}, trigger, services)

        assert result.data["person_detections"][0]["source_media_path"] == "http://minio/frame0.jpg"

    async def test_source_media_path_skipped_when_frame_index_out_of_range(self):
        det = _make_detection(frame_index=99)
        person_tracking = _make_person_tracking(detections=[det])
        trigger = _make_trigger(media_paths=["http://minio/frame0.jpg"])
        services = _make_services(person_tracking=person_tracking)

        result = await _HANDLER.execute(_make_step(), _FakeExecution(), {}, trigger, services)

        assert "source_media_path" not in result.data["person_detections"][0]


# ---------------------------------------------------------------------------
# Target-person filter
# ---------------------------------------------------------------------------


class TestTargetPersonFilter:
    async def test_continues_when_target_detected(self):
        det = _make_detection(person_id="alice", confidence=0.95)
        person_tracking = _make_person_tracking(detections=[det])
        services = _make_services(person_tracking=person_tracking)
        config = {"target_persons": ["alice"], "min_confidence": 0.6}

        result = await _HANDLER.execute(
            _make_step(config), _FakeExecution(), {}, _make_trigger(), services
        )

        assert result.should_continue is True
        assert "skip_reason" not in result.data

    async def test_short_circuits_when_target_not_detected(self):
        det = _make_detection(person_id="bob", confidence=0.95)
        person_tracking = _make_person_tracking(detections=[det])
        services = _make_services(person_tracking=person_tracking)
        config = {"target_persons": ["alice"], "min_confidence": 0.6}

        result = await _HANDLER.execute(
            _make_step(config), _FakeExecution(), {}, _make_trigger(), services
        )

        assert result.should_continue is False
        assert result.data["skip_reason"] == "target_person_not_detected"

    async def test_short_circuits_when_confidence_below_threshold(self):
        det = _make_detection(person_id="alice", confidence=0.3)
        person_tracking = _make_person_tracking(detections=[det])
        services = _make_services(person_tracking=person_tracking)
        config = {"target_persons": ["alice"], "min_confidence": 0.6}

        result = await _HANDLER.execute(
            _make_step(config), _FakeExecution(), {}, _make_trigger(), services
        )

        assert result.should_continue is False

    async def test_no_filter_when_target_persons_empty(self):
        det = _make_detection(person_id="alice", confidence=0.3)
        person_tracking = _make_person_tracking(detections=[det])
        services = _make_services(person_tracking=person_tracking)
        config = {"target_persons": []}

        result = await _HANDLER.execute(
            _make_step(config), _FakeExecution(), {}, _make_trigger(), services
        )

        assert result.should_continue is True

    async def test_room_transitions_present_even_on_short_circuit(self):
        """room_transitions must be populated even when the pipeline is halted."""
        det = _make_detection(person_id="bob", confidence=0.95)
        transition = _make_transition(person_id="bob")
        person_tracking = _make_person_tracking(detections=[det], transitions=[transition])
        services = _make_services(person_tracking=person_tracking)
        config = {"target_persons": ["alice"]}

        result = await _HANDLER.execute(
            _make_step(config), _FakeExecution(), {}, _make_trigger(), services
        )

        assert result.should_continue is False
        assert len(result.data["room_transitions"]) == 1


# ---------------------------------------------------------------------------
# process_camera_event call forwarding
# ---------------------------------------------------------------------------


class TestCallForwarding:
    async def test_sensor_id_forwarded(self):
        person_tracking = _make_person_tracking()
        services = _make_services(person_tracking=person_tracking)

        await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(sensor_id="cam-42"), services
        )

        call_kwargs = person_tracking.process_camera_event.call_args.kwargs
        assert call_kwargs["sensor_id"] == "cam-42"

    async def test_room_name_forwarded(self):
        person_tracking = _make_person_tracking()
        services = _make_services(person_tracking=person_tracking)

        await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(room_name="Bedroom"), services
        )

        call_kwargs = person_tracking.process_camera_event.call_args.kwargs
        assert call_kwargs["room_name"] == "Bedroom"

    async def test_include_annotated_image_forwarded(self):
        person_tracking = _make_person_tracking()
        services = _make_services(person_tracking=person_tracking)
        config = {"include_annotated_image": True}

        await _HANDLER.execute(_make_step(config), _FakeExecution(), {}, _make_trigger(), services)

        call_kwargs = person_tracking.process_camera_event.call_args.kwargs
        assert call_kwargs["include_annotated_image"] is True

    async def test_unknown_sensor_id_uses_fallback(self):
        """trigger.sensor_id=None should produce sensor_id='unknown' in the call."""
        person_tracking = _make_person_tracking()
        services = _make_services(person_tracking=person_tracking)

        trigger = _make_trigger(sensor_id=None)
        await _HANDLER.execute(_make_step(), _FakeExecution(), {}, trigger, services)

        call_kwargs = person_tracking.process_camera_event.call_args.kwargs
        assert call_kwargs["sensor_id"] == "unknown"


# ---------------------------------------------------------------------------
# Downstream image source + presence recording (Milestone 5)
# ---------------------------------------------------------------------------


def _mock_minio() -> MagicMock:
    minio = MagicMock(spec=MinioClient)
    minio.generate_presigned_url = lambda k, expiration=3600: f"http://minio/bucket/{k}?sig=test"
    minio.extract_object_name = lambda u: (
        u.split("/bucket/", 1)[1].split("?", 1)[0] if "/bucket/" in u else u
    )
    return minio


class TestDownstreamImageSources:
    @pytest.mark.asyncio
    async def test_pipeline_image_source_uses_crop_output_images(self):
        person_tracking = _make_person_tracking(detections=[_make_detection()])
        services = _make_services(person_tracking=person_tracking, minio_client=_mock_minio())

        pipeline_data = {
            "steps": {
                "crop_stove": {
                    "outputs": {
                        "images": ["http://minio/crops/stove.jpg"],
                    }
                }
            }
        }
        config = {
            "image_source": "pipeline",
            "pipeline_image_path": "steps.crop_stove.outputs.images",
        }
        result = await _HANDLER.execute(
            _make_step(config),
            _FakeExecution(),
            pipeline_data,
            _make_trigger(),
            services,
        )
        assert len(result.data["person_detections"]) == 1
        call_kwargs = person_tracking.process_camera_event.call_args.kwargs
        assert call_kwargs["media_paths"] == ["http://minio/crops/stove.jpg"]

    @pytest.mark.asyncio
    async def test_pipeline_image_source_uses_minio_key_frames(self):
        person_tracking = _make_person_tracking(detections=[_make_detection()])
        minio = _mock_minio()
        services = _make_services(person_tracking=person_tracking, minio_client=minio)

        pipeline_data = {
            "steps": {
                "media_window_poll_1": {
                    "outputs": {
                        "frames": [
                            {
                                "minio_key": "cts/cam1/frame.jpg",
                                "camera_id": "cam1",
                                "room_name": "Living Room",
                            }
                        ]
                    }
                }
            }
        }
        config = {
            "image_source": "pipeline",
            "pipeline_image_path": "steps.media_window_poll_1.outputs.frames",
            "presence_room_source": "source_image",
        }
        result = await _HANDLER.execute(
            _make_step(config),
            _FakeExecution(),
            pipeline_data,
            _make_trigger(),
            services,
        )
        assert len(result.data["person_detections"]) == 1
        call_kwargs = person_tracking.process_camera_event.call_args.kwargs
        assert call_kwargs["frame_contexts"] is not None
        assert call_kwargs["frame_contexts"][0].room_name == "Living Room"

    @pytest.mark.asyncio
    async def test_detection_includes_crop_region_metadata(self):
        det = _make_detection(frame_index=0)
        person_tracking = _make_person_tracking(detections=[det])
        services = _make_services(person_tracking=person_tracking, minio_client=_mock_minio())

        pipeline_data = {
            "steps": {
                "crop_stove": {
                    "outputs": {
                        "cropped_images": [
                            {
                                "url": "http://minio/crops/stove.jpg",
                                "object_name": "pipeline/crops/stove.jpg",
                                "region_id": "stove",
                                "region_name": "Stove area",
                                "source_sensor_id": "kitchen_cam",
                                "source_room_name": "Kitchen",
                            }
                        ]
                    }
                }
            }
        }
        config = {
            "image_source": "pipeline",
            "pipeline_image_path": "steps.crop_stove.outputs.cropped_images",
        }
        result = await _HANDLER.execute(
            _make_step(config),
            _FakeExecution(),
            pipeline_data,
            _make_trigger(),
            services,
        )
        d = result.data["person_detections"][0]
        assert d.get("crop_region_id") == "stove"
        assert d.get("crop_region_name") == "Stove area"
        assert d.get("source_sensor_id") == "kitchen_cam"


class TestPresenceRecording:
    @pytest.mark.asyncio
    async def test_presence_room_source_custom_uses_configured_room(self):
        person_tracking = _make_person_tracking(detections=[_make_detection()])
        services = _make_services(person_tracking=person_tracking)

        config = {
            "presence_room_source": "custom",
            "presence_room_name": "Living Room",
            "image_source": "trigger",
        }
        trigger = _make_trigger(room_name="Kitchen")
        await _HANDLER.execute(
            _make_step(config),
            _FakeExecution(),
            {},
            trigger,
            services,
        )
        call_kwargs = person_tracking.process_camera_event.call_args.kwargs
        ctx = call_kwargs["frame_contexts"][0]
        assert ctx.room_name == "Living Room"

    @pytest.mark.asyncio
    async def test_presence_room_source_source_image_uses_ref_room(self):
        person_tracking = _make_person_tracking(detections=[_make_detection()])
        minio = _mock_minio()
        services = _make_services(person_tracking=person_tracking, minio_client=minio)

        pipeline_data = {
            "steps": {
                "media_window_poll_1": {
                    "outputs": {
                        "frames": [
                            {
                                "minio_key": "cts/cam1/frame.jpg",
                                "camera_id": "cam1",
                                "room_name": "Bedroom",
                            }
                        ]
                    }
                }
            }
        }
        config = {
            "image_source": "pipeline",
            "pipeline_image_path": "steps.media_window_poll_1.outputs.frames",
            "presence_room_source": "source_image",
        }
        trigger = _make_trigger(room_name="Kitchen")
        await _HANDLER.execute(
            _make_step(config),
            _FakeExecution(),
            pipeline_data,
            trigger,
            services,
        )
        call_kwargs = person_tracking.process_camera_event.call_args.kwargs
        ctx = call_kwargs["frame_contexts"][0]
        # source_image room takes precedence over trigger room
        assert ctx.room_name == "Bedroom"

    @pytest.mark.asyncio
    async def test_default_config_preserves_trigger_source(self):
        person_tracking = _make_person_tracking(detections=[_make_detection()])
        services = _make_services(person_tracking=person_tracking)

        trigger = _make_trigger(sensor_id="cam-kitchen", room_name="Kitchen")
        await _HANDLER.execute(
            _make_step(),
            _FakeExecution(),
            {},
            trigger,
            services,
        )
        call_kwargs = person_tracking.process_camera_event.call_args.kwargs
        # Default: sensor_id and room_name from trigger
        assert call_kwargs["sensor_id"] == "cam-kitchen"
        assert call_kwargs["room_name"] == "Kitchen"


class TestOutputSchema:
    def test_output_conforms_to_schema(self):
        from backend.steps._testing import assert_output_conforms_to_schema
        from backend.steps.base import StepResult

        result = StepResult(
            data={
                "person_detections": [],
                "room_transitions": [],
                "annotated_image": None,
                "semantic_memory_movement_ids": None,
                "skip_reason": None,
            },
        )
        assert_output_conforms_to_schema(_HANDLER, result)
