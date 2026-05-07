"""Tests for SceneSampleSubscriber."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from backend.integrations.proto.continuoustracking.v1 import scene_pb2
from backend.integrations.scene_analysis_client import (
    SceneAnalyzeResult,
    SceneDetection,
    SceneHazardAlert,
)
from backend.integrations.semantic_memory_client import ObservationCreate, ObservationRecord
from backend.services.cts.scene_sample_subscriber import SceneSampleSubscriber


def _make_sample_proto(**overrides) -> scene_pb2.SceneSample:
    sample = scene_pb2.SceneSample()
    sample.keyframe_id = overrides.get("keyframe_id", "kf-001")
    sample.tracklet_id = overrides.get("tracklet_id", "trk-001")
    sample.global_track_id = overrides.get("global_track_id", "gtrk-001")
    sample.camera_id = overrides.get("camera_id", "cam-kitchen")
    sample.minio_key = overrides.get("minio_key", "keyframes/cam-kitchen/kf-001.jpg")
    sample.captured_at_unix_ns = overrides.get("captured_at_unix_ns", 1715000000000000000)
    sample.tag_reason = overrides.get("tag_reason", scene_pb2.TAG_REASON_PERIODIC)
    sample.annotations_json = overrides.get("annotations_json", "{}")
    sample.expires_at_unix_ns = overrides.get("expires_at_unix_ns", 1715003600000000000)
    return sample


def _make_raw_fields(sample: scene_pb2.SceneSample) -> dict:
    return {b"sample": sample.SerializeToString()}


def _make_analysis_result():
    return SceneAnalyzeResult(
        detections=[
            SceneDetection(label="stove", confidence=0.9, bbox=[10, 20, 30, 40], class_id=1),
            SceneDetection(label="person", confidence=0.95, bbox=[50, 60, 70, 80], class_id=2),
        ],
        description="A person standing near a stove in the kitchen.",
        embedding=[0.1, 0.2, 0.3],
        hazards=[
            SceneHazardAlert(
                name="stove_unattended",
                severity="warning",
                description="Stove appears unattended with cookware on burner.",
                detection=SceneDetection(label="stove", confidence=0.9, bbox=[10, 20, 30, 40], class_id=1),
            ),
        ],
        detector_available=True,
        describer_available=True,
        embedder_available=True,
    )


class TestSceneSampleDecode:
    async def test_decode_valid_message(self):
        sub = SceneSampleSubscriber(redis_url="redis://x", consumer_id="t1")
        sample = _make_sample_proto()
        fields = _make_raw_fields(sample)
        result = sub.decode(b"msg-1", fields)
        assert result is not None
        assert result["keyframe_id"] == "kf-001"
        assert result["camera_id"] == "cam-kitchen"
        assert result["minio_key"] == "keyframes/cam-kitchen/kf-001.jpg"
        assert result["tag_reason"] == "TAG_REASON_PERIODIC"

    async def test_decode_missing_payload_returns_none(self):
        sub = SceneSampleSubscriber(redis_url="redis://x", consumer_id="t1")
        result = sub.decode(b"msg-1", {})
        assert result is None

    async def test_decode_corrupt_proto_returns_none(self):
        sub = SceneSampleSubscriber(redis_url="redis://x", consumer_id="t1")
        result = sub.decode(b"msg-1", {b"sample": b"not-a-valid-proto"})
        assert result is None

    async def test_decode_string_payload(self):
        sub = SceneSampleSubscriber(redis_url="redis://x", consumer_id="t1")
        sample = _make_sample_proto()
        fields = {"sample": sample.SerializeToString().decode("latin-1")}
        result = sub.decode(b"msg-1", fields)
        assert result is not None
        assert result["keyframe_id"] == "kf-001"


class TestSceneSampleHandle:
    async def test_full_pipeline_success(self):
        minio = MagicMock()
        minio.get_object.return_value = b"fake-jpeg-bytes"

        analysis = MagicMock()
        analysis.configured = True
        analysis.analyze = AsyncMock(return_value=_make_analysis_result())

        memory = MagicMock()
        memory.configured = True
        memory.create_observation = AsyncMock(
            return_value=ObservationRecord(
                id=42, room_id="kitchen", description="test",
                object_list=["stove"], hazard_flags=["stove_unattended"],
                observed_at=None, source="scene_intel", created_at=None,
            )
        )

        sub = SceneSampleSubscriber(
            redis_url="redis://x",
            consumer_id="t1",
            minio_client=minio,
            scene_analysis_client=analysis,
            semantic_memory_client=memory,
        )

        sample = {
            "keyframe_id": "kf-001",
            "camera_id": "cam-kitchen",
            "minio_key": "keyframes/kf-001.jpg",
            "tag_reason": "TAG_REASON_PERIODIC",
        }

        result = await sub.handle(sample)
        assert result  # not a coroutine
        minio.get_object.assert_called_once_with("keyframes/kf-001.jpg")
        analysis.analyze.assert_called_once()
        memory.create_observation.assert_called_once()

        obs: ObservationCreate = memory.create_observation.call_args.args[0]
        assert obs.source == "scene_intel"
        assert "stove" in obs.object_list
        assert "stove_unattended" in obs.hazard_flags
        assert len(obs.embedding) == 3

    async def test_minio_miss_acks_and_skips(self):
        minio = MagicMock()
        minio.get_object.side_effect = FileNotFoundError("no such key")

        analysis = MagicMock()
        analysis.configured = True

        sub = SceneSampleSubscriber(
            redis_url="redis://x",
            consumer_id="t1",
            minio_client=minio,
            scene_analysis_client=analysis,
        )

        sample = {"keyframe_id": "kf-001", "camera_id": "cam-kitchen", "minio_key": "bad-key"}
        result = await sub.handle(sample)
        assert result is True  # acked; not retried

    async def test_analysis_not_configured_skips(self):
        minio = MagicMock()
        minio.get_object.return_value = b"jpeg"

        analysis = MagicMock()
        analysis.configured = False

        memory = MagicMock()
        memory.configured = True
        memory.create_observation = AsyncMock(
            return_value=ObservationRecord(
                id=1, room_id="", description="", object_list=[],
                hazard_flags=[], observed_at=None, source="scene_intel", created_at=None,
            )
        )

        sub = SceneSampleSubscriber(
            redis_url="redis://x",
            consumer_id="t1",
            minio_client=minio,
            scene_analysis_client=analysis,
            semantic_memory_client=memory,
        )

        sample = {"keyframe_id": "kf-001", "camera_id": "cam-kitchen", "minio_key": "kf.jpg"}
        result = await sub.handle(sample)
        assert result is True
        analysis.analyze.assert_not_called()
        # Still persists to memory (empty observation)
        memory.create_observation.assert_called_once()

    async def test_no_minio_client_acks(self):
        sub = SceneSampleSubscriber(redis_url="redis://x", consumer_id="t1")
        sample = {"keyframe_id": "kf-001", "camera_id": "cam-kitchen", "minio_key": "kf.jpg"}
        result = await sub.handle(sample)
        assert result is True

    async def test_no_semantic_memory_client_skips_persist(self):
        minio = MagicMock()
        minio.get_object.return_value = b"jpeg"

        analysis = MagicMock()
        analysis.configured = True
        analysis.analyze = AsyncMock(return_value=_make_analysis_result())

        sub = SceneSampleSubscriber(
            redis_url="redis://x",
            consumer_id="t1",
            minio_client=minio,
            scene_analysis_client=analysis,
        )

        sample = {"keyframe_id": "kf-001", "camera_id": "cam-kitchen", "minio_key": "kf.jpg"}
        result = await sub.handle(sample)
        assert result is True
        analysis.analyze.assert_called_once()

    async def test_empty_minio_object_acks(self):
        minio = MagicMock()
        minio.get_object.return_value = b""

        sub = SceneSampleSubscriber(
            redis_url="redis://x", consumer_id="t1", minio_client=minio
        )

        sample = {"keyframe_id": "kf-001", "camera_id": "cam-kitchen", "minio_key": "kf.jpg"}
        result = await sub.handle(sample)
        assert result is True

    async def test_analysis_exception_does_not_crash(self):
        minio = MagicMock()
        minio.get_object.return_value = b"jpeg"

        analysis = MagicMock()
        analysis.configured = True
        analysis.analyze = AsyncMock(side_effect=RuntimeError("service down"))

        memory = MagicMock()
        memory.configured = True
        memory.create_observation = AsyncMock(
            return_value=ObservationRecord(
                id=1, room_id="", description="", object_list=[],
                hazard_flags=[], observed_at=None, source="scene_intel", created_at=None,
            )
        )

        sub = SceneSampleSubscriber(
            redis_url="redis://x",
            consumer_id="t1",
            minio_client=minio,
            scene_analysis_client=analysis,
            semantic_memory_client=memory,
        )

        sample = {"keyframe_id": "kf-001", "camera_id": "cam-kitchen", "minio_key": "kf.jpg"}
        result = await sub.handle(sample)
        assert result is True
        # Still creates empty observation
        memory.create_observation.assert_called_once()
