"""SceneSampleSubscriber: consume scene.samples and persist to semantic memory.

Decodes ``SceneSample`` proto messages from the ``scene.samples`` Redis
Stream, pulls the tagged keyframe JPEG from MinIO, runs scene analysis,
and creates an observation in semantic memory.

Wire format: each Redis Streams message carries one field, ``sample``,
whose value is the raw protobuf body of a
``continuoustracking.v1.SceneSample``.
"""

from __future__ import annotations

from typing import Any

from backend.core.logging import get_logger
from backend.integrations.proto.continuoustracking.v1 import scene_pb2
from backend.services.cts import metrics
from backend.services.cts._time import ns_to_iso
from backend.services.cts._types import MinioClient, SceneAnalysisClient, SemanticMemoryClient
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer

logger = get_logger(__name__)

FIELD = b"sample"


class SceneSampleSubscriber(StreamConsumer[dict[str, Any]]):
    """Consume ``scene.samples``, analyse, and persist to semantic memory."""

    STREAM = "scene.samples"
    GROUP = "cognitive-companion-scene-samples"

    def __init__(
        self,
        *,
        redis_url: str,
        consumer_id: str,
        minio_client: MinioClient | None = None,
        scene_analysis_client: SceneAnalysisClient | None = None,
        semantic_memory_client: SemanticMemoryClient | None = None,
        camera_room_map: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            ConsumerConfig(
                redis_url=redis_url,
                stream=self.STREAM,
                group=self.GROUP,
                consumer_id=consumer_id,
                concurrency=1,
            )
        )
        self._minio = minio_client
        self._scene_analysis = scene_analysis_client
        self._semantic_memory = semantic_memory_client
        self._camera_room_map = camera_room_map or {}

    # -- StreamConsumer abstract methods ----------------------------------

    def decode(
        self, message_id: bytes, fields: dict[bytes | str, bytes | str]
    ) -> dict[str, Any] | None:
        payload = fields.get(FIELD) or fields.get(FIELD.decode())
        if payload is None:
            logger.warning("scene_sample_missing_payload", message_id=message_id)
            return None
        if isinstance(payload, str):
            payload = payload.encode("latin-1")

        try:
            message = scene_pb2.SceneSample.FromString(payload)
        except Exception:
            logger.warning("scene_sample_proto_decode_error", message_id=message_id)
            metrics.cts_events_decode_errors.inc()
            return None

        return {
            "keyframe_id": message.keyframe_id,
            "tracklet_id": message.tracklet_id,
            "global_track_id": message.global_track_id,
            "camera_id": message.camera_id,
            "minio_key": message.minio_key,
            "captured_at": ns_to_iso(message.captured_at_unix_ns),
            "tag_reason": scene_pb2.TagReason.Name(message.tag_reason),
            "annotations_json": message.annotations_json or "{}",
            "expires_at": ns_to_iso(message.expires_at_unix_ns)
            if message.expires_at_unix_ns
            else None,
        }

    async def handle(self, sample: dict[str, Any]) -> bool:
        minio_key = sample.get("minio_key", "")
        camera_id = sample.get("camera_id", "unknown")
        reason = sample.get("tag_reason", "UNSPECIFIED")

        logger.info(
            "scene_sample_received",
            keyframe_id=sample.get("keyframe_id"),
            camera_id=camera_id,
            tag_reason=reason,
        )

        if not minio_key or not self._minio:
            logger.warning("scene_sample_skipped_no_minio", camera_id=camera_id)
            return True  # ack and drop; can't process without MinIO

        # 1. Pull JPEG from MinIO -------------------------------------------------
        try:
            image_bytes = await self._minio.async_get_object(minio_key)
        except Exception:
            logger.exception("scene_sample_minio_fetch_error", minio_key=minio_key)
            return True  # ack; don't retry a missing object

        if not image_bytes:
            logger.warning("scene_sample_empty_object", minio_key=minio_key)
            return True

        # 2. Resolve camera_id -> room -------------------------------------------
        room_id = self._camera_room_map.get(camera_id, "")

        # 3. Scene analysis -------------------------------------------------------
        description = ""
        object_list: list[str] = []
        embedding: list[float] = []
        hazard_flags: list[str] = []

        if self._scene_analysis and self._scene_analysis.configured:
            try:
                result = await self._scene_analysis.analyze(
                    image_bytes,
                    run_detect=True,
                    run_describe=True,
                    run_embed=True,
                    run_hazards=True,
                    sensor_id=camera_id,
                )
                description = result.description or ""
                object_list = [d.label for d in (result.detections or [])]
                embedding = result.embedding or []
                hazard_flags = [h.name for h in (result.hazards or [])]
            except Exception:
                logger.exception(
                    "scene_sample_analysis_error",
                    camera_id=camera_id,
                    keyframe_id=sample.get("keyframe_id"),
                )
        else:
            logger.debug("scene_sample_analysis_skipped", camera_id=camera_id)

        # 4. Persist to semantic memory -------------------------------------------
        observation_id: int | None = None

        if self._semantic_memory and self._semantic_memory.configured:
            try:
                from backend.integrations.semantic_memory_client import ObservationCreate

                record = await self._semantic_memory.create_observation(
                    ObservationCreate(
                        room_id=room_id,
                        description=description,
                        object_list=object_list,
                        hazard_flags=hazard_flags,
                        embedding=embedding,
                        source="scene_intel",
                    )
                )
                if record:
                    observation_id = record.id
                    logger.info(
                        "scene_sample_observation_created",
                        observation_id=observation_id,
                        camera_id=camera_id,
                        room_id=room_id,
                        objects=len(object_list),
                        hazards=len(hazard_flags),
                    )
            except Exception:
                logger.exception(
                    "scene_sample_memory_persist_error",
                    camera_id=camera_id,
                )
        else:
            logger.debug("scene_sample_memory_skipped", camera_id=camera_id)

        return True
