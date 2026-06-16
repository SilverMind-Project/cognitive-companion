"""Image crop pipeline step.

Crops configured regions from input images and writes the results to MinIO.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO

from PIL import Image

from backend.core.logging import get_logger
from backend.models.media_cache import MediaCache
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.steps import StepRegistry
from backend.steps._pipeline_images import (
    PipelineImageRef,
    fetch_image_bytes,
    resolve_pipeline_image_refs,
)
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)

_MIN_CROP_PX = 8


@StepRegistry.register
class ImageCropHandler(StepHandler):
    """Crop configured regions from pipeline images and write results to MinIO."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="image_crop",
            display_name="Crop Image",
            category="perception",
            icon="mdi-crop",
            description="Crop configured regions from pipeline images and write the results to MinIO.",
            tags=("image", "crop", "media"),
            config_schema={
                "type": "object",
                "properties": {
                    "image_source": {
                        "type": "string",
                        "enum": [
                            "trigger",
                            "additional",
                            "both",
                            "pipeline",
                            "media_window",
                            "cts_window",
                        ],
                        "default": "trigger",
                    },
                    "pipeline_image_path": {"type": "string", "default": ""},
                    "cts_frames_path": {
                        "type": "string",
                        "default": "steps.media_window_poll_1.outputs.frames",
                    },
                    "max_images": {"type": "integer", "minimum": 1, "default": 1},
                    "trigger_images_count": {"type": "integer", "minimum": 0, "default": 0},
                    "additional_sensor_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                    },
                    "additional_room_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                    },
                    "images_per_sensor": {"type": "integer", "minimum": 1, "default": 1},
                    "sensor_frame_limits": {"type": "object", "default": {}},
                    "image_time_filter": {"type": "object", "default": {}},
                    "regions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["id", "name", "x", "y", "width", "height"],
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "pattern": "^[a-z][a-z0-9_]*$",
                                },
                                "name": {"type": "string"},
                                "x": {"type": "number", "minimum": 0, "maximum": 1},
                                "y": {"type": "number", "minimum": 0, "maximum": 1},
                                "width": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
                                "height": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
                            },
                        },
                        "default": [],
                    },
                    "output_format": {"type": "string", "enum": ["jpeg"], "default": "jpeg"},
                    "jpeg_quality": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 90,
                    },
                    "retention_minutes": {
                        "type": "integer",
                        "minimum": 5,
                        "maximum": 1440,
                        "default": 60,
                    },
                },
            },
            default_config={
                "image_source": "trigger",
                "pipeline_image_path": "",
                "cts_frames_path": "steps.media_window_poll_1.outputs.frames",
                "max_images": 1,
                "trigger_images_count": 0,
                "additional_sensor_ids": [],
                "additional_room_names": [],
                "images_per_sensor": 1,
                "sensor_frame_limits": {},
                "image_time_filter": {},
                "regions": [],
                "output_format": "jpeg",
                "jpeg_quality": 90,
                "retention_minutes": 60,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "images": {"type": "array", "items": {"type": "string"}},
                    "cropped_images": {"type": "array", "items": {"type": "object"}},
                    "count": {"type": "integer"},
                    "skipped": {"type": "array", "items": {"type": "object"}},
                    "cropped_at": {"type": "string"},
                },
                "required": ["images", "cropped_images", "count", "skipped", "cropped_at"],
            },
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        if services.minio_client is None:
            return StepResult(
                success=False,
                data={
                    "images": [],
                    "cropped_images": [],
                    "count": 0,
                    "skipped": [{"reason": "minio_unavailable"}],
                    "cropped_at": datetime.now(UTC).isoformat(),
                    "error": "MinIO client is not available",
                },
            )

        config = step.config_json or {}

        # Resolve input image refs.
        refs = await resolve_pipeline_image_refs(
            config,
            pipeline_data,
            trigger,
            services,
            default_max_images=int(config.get("max_images", 1)),
        )

        if not refs:
            return StepResult(
                data={
                    "images": [],
                    "cropped_images": [],
                    "count": 0,
                    "skipped": [],
                    "cropped_at": datetime.now(UTC).isoformat(),
                },
            )

        regions: list[dict] = config.get("regions") or []
        if not regions:
            return StepResult(
                data={
                    "images": [],
                    "cropped_images": [],
                    "count": 0,
                    "skipped": [{"reason": "no_regions"}],
                    "cropped_at": datetime.now(UTC).isoformat(),
                },
            )

        jpeg_quality: int = int(config.get("jpeg_quality", 90))
        retention_minutes: int = int(config.get("retention_minutes", 60))
        max_images: int = int(config.get("max_images", 1))

        cropped_images: list[dict] = []
        skipped: list[dict] = []

        for source_index, ref in enumerate(refs[:max_images]):
            image_bytes = await fetch_image_bytes(ref, services.minio_client)
            if image_bytes is None:
                skipped.append(
                    {
                        "reason": "fetch_failed",
                        "source_index": source_index,
                        "source_url": ref.url,
                        "source_object_name": ref.object_name,
                    }
                )
                continue

            try:
                img = Image.open(BytesIO(image_bytes))
                img.load()
            except Exception:  # noqa: BLE001
                logger.warning(
                    "image_decode_error", ref_url=ref.url, ref_object_name=ref.object_name
                )
                skipped.append(
                    {
                        "reason": "decode_failed",
                        "source_index": source_index,
                        "source_url": ref.url,
                        "source_object_name": ref.object_name,
                    }
                )
                continue

            original_width, original_height = img.size

            for region in regions:
                region_id: str = region["id"]
                region_name: str = region.get("name", region_id)

                # Convert ratios to pixel bounds.
                left = round(float(region["x"]) * original_width)
                top = round(float(region["y"]) * original_height)
                right = round((float(region["x"]) + float(region["width"])) * original_width)
                bottom = round((float(region["y"]) + float(region["height"])) * original_height)

                # Clamp to image bounds.
                left = max(0, min(left, original_width))
                top = max(0, min(top, original_height))
                right = max(0, min(right, original_width))
                bottom = max(0, min(bottom, original_height))

                crop_w = right - left
                crop_h = bottom - top

                if crop_w < _MIN_CROP_PX or crop_h < _MIN_CROP_PX:
                    skipped.append(
                        {
                            "reason": "region_too_small",
                            "source_index": source_index,
                            "region_id": region_id,
                            "region_name": region_name,
                            "crop_width": crop_w,
                            "crop_height": crop_h,
                            "clamped_bounds": {
                                "left": left,
                                "top": top,
                                "right": right,
                                "bottom": bottom,
                            },
                        }
                    )
                    continue

                cropped = img.crop((left, top, right, bottom))

                # Encode as JPEG (only supported format for now).
                output_buf = BytesIO()
                cropped.save(output_buf, format="JPEG", quality=jpeg_quality)
                crop_bytes = output_buf.getvalue()

                object_name = (
                    f"pipeline/crops/{execution.id}/{step.id}/"
                    f"{region_id}_{source_index}_{uuid.uuid4().hex[:8]}.jpg"
                )

                try:
                    presigned_url = await services.minio_client.async_upload_bytes(
                        crop_bytes, object_name, "image/jpeg"
                    )
                except Exception:
                    logger.exception("crop_upload_error", object_name=object_name)
                    skipped.append(
                        {
                            "reason": "upload_failed",
                            "source_index": source_index,
                            "region_id": region_id,
                            "object_name": object_name,
                        }
                    )
                    continue

                self._register_media_cache(
                    services,
                    object_name,
                    presigned_url,
                    ref,
                    retention_minutes,
                )

                source_object_name = ref.object_name
                if source_object_name is None and ref.url and services.minio_client:
                    source_object_name = services.minio_client.extract_object_name(ref.url)

                entry = {
                    "url": presigned_url,
                    "object_name": object_name,
                    "region_id": region_id,
                    "region_name": region_name,
                    "source_type": ref.source_type,
                    "source_sensor_id": ref.source_sensor_id,
                    "source_camera_id": ref.source_camera_id,
                    "source_room_name": ref.source_room_name,
                    "source_object_name": source_object_name,
                    "original_width": original_width,
                    "original_height": original_height,
                    "output_width": crop_w,
                    "output_height": crop_h,
                    "crop_box": {
                        "unit": "ratio",
                        "x": float(region["x"]),
                        "y": float(region["y"]),
                        "width": float(region["width"]),
                        "height": float(region["height"]),
                    },
                }
                cropped_images.append(entry)

        return StepResult(
            data={
                "images": [ci["url"] for ci in cropped_images],
                "cropped_images": cropped_images,
                "count": len(cropped_images),
                "skipped": skipped,
                "cropped_at": datetime.now(UTC).isoformat(),
            },
        )

    # ------------------------------------------------------------------
    # MediaCache registration
    # ------------------------------------------------------------------

    @staticmethod
    def _register_media_cache(
        services: ServiceContainer,
        object_name: str,
        presigned_url: str,
        source_ref: PipelineImageRef,
        retention_minutes: int,
    ) -> None:
        """Persist a MediaCache row so the crop is tracked for cleanup."""
        now = datetime.now(UTC)
        sensor_id = source_ref.source_sensor_id or source_ref.source_camera_id or None

        db = services.db_factory()
        try:
            row = db.query(MediaCache).filter(MediaCache.object_name == object_name).first()
            if row is None:
                row = MediaCache(
                    object_name=object_name,
                    presigned_url=presigned_url,
                    sensor_id=sensor_id,
                    captured_at=now,
                    expires_at=now + timedelta(minutes=retention_minutes),
                )
                db.add(row)
            else:
                row.presigned_url = presigned_url
                row.sensor_id = sensor_id
                row.expires_at = now + timedelta(minutes=retention_minutes)
            db.commit()
        except Exception:
            logger.exception("media_cache_register_error", object_name=object_name)
            db.rollback()
        finally:
            db.close()
