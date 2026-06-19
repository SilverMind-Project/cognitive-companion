"""Shared pipeline image reference resolution.

Provides a typed helper layer that normalizes image inputs from trigger
media, reCamera EventAggregator queries, CTS frame dicts, and prior step
outputs into :class:`PipelineImageRef` so that scene_analysis, llm_call,
person_identification, and the future image_crop step consume a single
shape.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx

from backend.core.logging import get_logger
from backend.services.pipeline_data_manager import resolve_pipeline_value

logger = get_logger(__name__)

if TYPE_CHECKING:
    from backend.integrations.minio_client import MinioClient
    from backend.steps.base import ServiceContainer, TriggerContext

# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineImageRef:
    """Normalised reference to a pipeline-consumable image."""

    url: str | None = None
    object_name: str | None = None
    source_type: str = "unknown"
    source_sensor_id: str | None = None
    source_camera_id: str | None = None
    source_room_name: str | None = None
    width: int | None = None
    height: int | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_URL_SCHEME_PREFIXES = ("http://", "https://", "data:")


def _looks_like_url(value: str) -> bool:
    return value.startswith(_URL_SCHEME_PREFIXES)


def _as_int(value: object, default: int) -> int:
    """Coerce an untyped config/JSON value to int, falling back to *default*."""
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _as_float_or_none(value: object) -> float | None:
    """Coerce an untyped config/JSON value to float, or None."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _as_str_or_none(value: object) -> str | None:
    """Coerce an untyped config/JSON value to str, or None."""
    return str(value) if value is not None else None


def _as_str_list(value: object) -> list[str]:
    """Coerce an untyped config/JSON value to a list of strings (else empty)."""
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return []


def _as_object_dict(value: object) -> dict[str, object]:
    """Coerce an untyped config/JSON value to a str-keyed dict (else empty)."""
    if isinstance(value, Mapping):
        return {str(k): v for k, v in value.items()}
    return {}


def _normalize_dict(
    value: Mapping[str, object], *, default_source_type: str
) -> list[PipelineImageRef]:
    """Normalize a single dict value into PipelineImageRef(s).

    Handles CTS frame dicts (``minio_key``), crop output dicts
    (``object_name`` + metadata), and simple URL-bearing dicts.

    Constructs the typed :class:`PipelineImageRef` directly (no untyped kwargs
    splat) so the boundary is fully type-checked. Precedence is preserved:
    source-identity fields take the last present alias (``camera_id`` overrides
    ``source_camera_id``); dimension fields take the first present alias.
    """

    def _last_present_str(*keys: str) -> str | None:
        result: str | None = None
        for key in keys:
            v = value.get(key)
            if v is not None:
                result = str(v)
        return result

    def _first_present_int(*keys: str) -> int | None:
        for key in keys:
            v = value.get(key)
            if isinstance(v, (int, float)):
                return int(v)
        return None

    # -- URL / object name resolution ----------------------------------------
    object_name: str | None = None
    if value.get("minio_key") is not None:
        object_name = str(value["minio_key"])
    elif value.get("object_name") is not None:
        object_name = str(value["object_name"])

    url: str | None = None
    if value.get("url") is not None:
        url = str(value["url"])
    elif value.get("image_url") is not None:
        url = str(value["image_url"])

    # Fallback: a bare ``image`` key (from media_window_poll outputs).
    if url is None and object_name is None:
        maybe_image = value.get("image")
        if isinstance(maybe_image, str):
            if _looks_like_url(maybe_image):
                url = maybe_image
            else:
                object_name = maybe_image

    # -- remaining metadata fields -------------------------------------------
    meta_fields = (
        "region_id",
        "region_name",
        "source_object_name",
        "output_width",
        "output_height",
        "crop_box",
    )
    metadata: dict[str, object] = {k: value[k] for k in meta_fields if k in value}

    return [
        PipelineImageRef(
            url=url,
            object_name=object_name,
            source_type=default_source_type,
            source_sensor_id=_last_present_str("source_sensor_id", "sensor_id"),
            source_camera_id=_last_present_str("source_camera_id", "camera_id"),
            source_room_name=_last_present_str("source_room_name", "room_name"),
            width=_first_present_int("frame_width", "original_width", "width"),
            height=_first_present_int("frame_height", "original_height", "height"),
            metadata=metadata,
        )
    ]


def normalize_image_value(
    value: object, *, default_source_type: str = "unknown"
) -> list[PipelineImageRef]:
    """Convert an input value into a list of :class:`PipelineImageRef`.

    Accepted shapes:

    * ``str`` -- treated as a URL if it starts with ``http://``, ``https://``,
      or ``data:``; otherwise treated as a MinIO object key.
    * ``dict`` with ``url``, ``image_url``, ``object_name``, or ``minio_key``.
    * ``list`` -- each element is normalised recursively and flattened.
    """
    if isinstance(value, str):
        if _looks_like_url(value):
            return [PipelineImageRef(url=value, source_type=default_source_type)]
        return [PipelineImageRef(object_name=value, source_type=default_source_type)]

    if isinstance(value, Mapping):
        return _normalize_dict(value, default_source_type=default_source_type)

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        result: list[PipelineImageRef] = []
        for item in value:
            result.extend(normalize_image_value(item, default_source_type=default_source_type))
        return result

    return []


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


async def resolve_pipeline_image_refs(
    config: Mapping[str, object],
    pipeline_data: Mapping[str, object],
    trigger: TriggerContext,
    services: ServiceContainer,
    *,
    default_image_source: str = "trigger",
    default_max_images: int = 5,
    default_images_per_sensor: int = 1,
    sort_by_sensor: bool = False,
) -> list[PipelineImageRef]:
    """Resolve image refs according to the step *config*.

    Supported ``image_source`` values:

    * ``trigger`` -- :attr:`TriggerContext.media_paths`
    * ``additional`` -- reCamera images from :class:`EventAggregator`
    * ``both`` -- trigger + additional
    * ``pipeline`` -- a prior step output path (read via *pipeline_image_path*)
    * ``media_window`` -- unified media-window output, preferring ``images`` then ``frames``
    * ``cts_window`` -- CTS frame dicts from a *cts_frames_path* path
    * ``none`` -- return empty list (for text-only LLM calls)

    The function returns an empty list when a service or path is missing
    rather than raising an exception.
    """
    image_source = str(config.get("image_source", default_image_source))

    if image_source == "none":
        return []

    refs: list[PipelineImageRef] = []

    # -- trigger -------------------------------------------------------------
    if image_source in ("trigger", "both"):
        media_paths = trigger.media_paths or []
        trigger_count = _as_int(config.get("trigger_images_count"), 0)
        if trigger_count > 0:
            media_paths = media_paths[-trigger_count:]
        for mp in media_paths:
            refs.extend(normalize_image_value(mp, default_source_type="trigger"))

    # -- additional (reCamera EventAggregator) -------------------------------
    if image_source in ("additional", "both") and services.event_aggregator:
        max_images = _as_int(config.get("max_images"), default_max_images)
        additional_sensors: list[str] = _as_str_list(config.get("additional_sensor_ids"))
        additional_rooms: list[str] = _as_str_list(config.get("additional_room_names"))
        time_filter: dict[str, object] = _as_object_dict(config.get("image_time_filter"))
        images_per_sensor = _as_int(config.get("images_per_sensor"), default_images_per_sensor)
        sensor_frame_limits: dict[str, int] = {
            k: _as_int(v, 0) for k, v in _as_object_dict(config.get("sensor_frame_limits")).items()
        }

        since_minutes = _as_float_or_none(time_filter.get("since_minutes"))
        time_start = _as_str_or_none(time_filter.get("time_start"))
        time_end = _as_str_or_none(time_filter.get("time_end"))

        extra: list[str] = []
        if additional_rooms:
            extra = await services.event_aggregator.query_recent_media(
                sensor_ids=additional_sensors if additional_sensors else None,
                room_names=additional_rooms,
                limit=max_images,
                since_minutes=since_minutes,
                time_start=time_start,
                time_end=time_end,
            )
        elif additional_sensors:
            extra = await services.event_aggregator.query_media_by_sensor(
                sensor_ids_ordered=additional_sensors,
                images_per_sensor=images_per_sensor,
                sensor_frame_limits=sensor_frame_limits,
                max_images=max_images,
                chronological=sort_by_sensor,
                since_minutes=since_minutes,
                time_start=time_start,
                time_end=time_end,
            )
        elif image_source == "additional":
            extra = await services.event_aggregator.query_recent_media(
                sensor_ids=None,
                room_names=None,
                limit=max_images,
                since_minutes=since_minutes,
                time_start=time_start,
                time_end=time_end,
            )

        for url in extra:
            refs.extend(normalize_image_value(url, default_source_type="additional"))

    # -- pipeline (prior step output) ---------------------------------------
    if image_source == "pipeline":
        path = str(config.get("pipeline_image_path", ""))
        if path:
            raw = resolve_pipeline_value(pipeline_data, path)
            if raw is not None:
                refs.extend(normalize_image_value(raw, default_source_type="pipeline"))

    # -- media_window (unified poll-step output) ----------------------------
    if image_source == "media_window":
        path = str(config.get("pipeline_image_path", ""))
        if path:
            raw = resolve_pipeline_value(pipeline_data, path)
            if isinstance(raw, Mapping):
                images = raw.get("images")
                frames = raw.get("frames")
                selected = images if images else frames
                if selected is not None:
                    refs.extend(
                        normalize_image_value(
                            selected,
                            default_source_type="media_window",
                        )
                    )
            elif raw is not None:
                refs.extend(normalize_image_value(raw, default_source_type="media_window"))

    # -- cts_window (CTS frame dicts) ---------------------------------------
    if image_source == "cts_window":
        path = str(config.get("cts_frames_path", ""))
        if path:
            raw = resolve_pipeline_value(pipeline_data, path)
            if raw is not None:
                refs.extend(normalize_image_value(raw, default_source_type="cts_window"))

    # -- apply max_images cap -----------------------------------------------
    max_images = _as_int(config.get("max_images"), default_max_images)
    if max_images > 0 and len(refs) > max_images:
        refs = refs[:max_images]

    # -- regenerate presigned URLs for refs with only object_name -----------
    if services.minio_client:
        for ref in refs:
            if ref.url is None and ref.object_name is not None:
                # Frozen dataclass -- use object.__setattr__
                object.__setattr__(
                    ref,
                    "url",
                    services.minio_client.generate_presigned_url(ref.object_name),
                )

    return refs


# ---------------------------------------------------------------------------
# URL extraction
# ---------------------------------------------------------------------------


def image_refs_to_urls(
    refs: list[PipelineImageRef], minio_client: MinioClient | None = None
) -> list[str]:
    """Extract URLs from a list of :class:`PipelineImageRef`.

    When *minio_client* is provided, refs that only carry an
    ``object_name`` get a fresh presigned URL.
    """
    urls: list[str] = []
    for ref in refs:
        url = ref.url
        if url is None and ref.object_name is not None and minio_client is not None:
            url = minio_client.generate_presigned_url(ref.object_name)
        if url is not None:
            urls.append(url)
    return urls


# ---------------------------------------------------------------------------
# Image byte fetching
# ---------------------------------------------------------------------------


async def fetch_image_bytes(
    ref: PipelineImageRef, minio_client: MinioClient | None
) -> bytes | None:
    """Fetch raw image bytes for *ref* from MinIO or via HTTP.

    Prefers MinIO direct access (by ``object_name``, or by extracting the
    key from a presigned URL).  Falls back to HTTP GET on ``ref.url``.
    Returns ``None`` on any failure.
    """
    if minio_client is not None:
        object_name = ref.object_name
        if object_name is None and ref.url:
            object_name = minio_client.extract_object_name(ref.url)
        if object_name:
            try:
                data = await minio_client.async_get_object(object_name)
                if data is not None:
                    return data
            except Exception:  # noqa: BLE001
                logger.warning("fetch_bytes_minio_error", object_name=object_name, exc_info=True)

    if ref.url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(ref.url)
                resp.raise_for_status()
                return resp.content
        except Exception:  # noqa: BLE001
            logger.warning("fetch_bytes_http_error", url=ref.url, exc_info=True)

    return None
