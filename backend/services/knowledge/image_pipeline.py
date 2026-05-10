"""Pillow-based image variant rendering, purge, and upload-time validation.

Operations per variant: download original, strip EXIF (honouring orientation),
colour convert, resize/fit per layout spec, encode, upload to MinIO.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO

from PIL import Image, ImageOps

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.services.knowledge.layout_registry import (
    ImageVariantSpec,
    LayoutRegistry,
)

logger = get_logger(__name__)

ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    settings.get("knowledge.allowed_mime_types", ["image/jpeg", "image/png"])
)
MAX_UPLOAD_BYTES: int = settings.get("knowledge.max_upload_bytes", 15728640)
MAX_PIXELS: int = settings.get("knowledge.max_pixels", 40000000)


@dataclass(frozen=True, slots=True)
class RenderedVariant:
    object_name: str
    width: int
    height: int
    format: str
    size_bytes: int
    generated_at: str


@dataclass(frozen=True, slots=True)
class PurgeResult:
    deleted_count: int
    failed_keys: list[str]


class ImagePipeline:
    """Variant renderer and MinIO cleanup for knowledge images."""

    def __init__(self, minio_client: MinioClient, layouts: LayoutRegistry) -> None:
        self._minio = minio_client
        self._layouts = layouts

    # -- variant rendering -------------------------------------------------

    async def render_variants(
        self,
        *,
        original_object_name: str,
        layout_id: str,
        slot_id: str,
        target_key_prefix: str,
    ) -> dict[str, RenderedVariant]:
        """For every (surface) declared by the layout slot, render a variant
        from the original and upload it to MinIO. Returns a dict keyed by
        surface name.
        """
        layout = self._layouts.get_required(layout_id)
        slot = _find_slot(layout, slot_id)

        original_bytes = self._minio.get_object(original_object_name)
        if original_bytes is None:
            raise FileNotFoundError(f"Original not found in MinIO: {original_object_name}")

        img: Image.Image = Image.open(BytesIO(original_bytes))
        # Honour EXIF orientation, then strip metadata
        img = ImageOps.exif_transpose(img)

        results: dict[str, RenderedVariant] = {}
        for surface, spec in slot.variants.items():
            variant = self._render_one(img, spec)
            object_name = f"{target_key_prefix}__{surface}.{spec.format}"
            content_type = _content_type_for(spec.format)
            buf = BytesIO()
            save_kwargs: dict = {"format": _pillow_format(spec.format)}
            if (spec.format == "webp" and spec.quality) or (spec.format == "jpeg" and spec.quality):
                save_kwargs["quality"] = spec.quality
            variant.save(buf, **save_kwargs)
            data = buf.getvalue()
            self._minio.upload_bytes(data, object_name, content_type)

            results[surface] = RenderedVariant(
                object_name=object_name,
                width=variant.width,
                height=variant.height,
                format=spec.format,
                size_bytes=len(data),
                generated_at=datetime.now(UTC).isoformat(),
            )

        return results

    # -- purge -------------------------------------------------------------

    async def purge_prefix(self, prefix: str) -> PurgeResult:
        """List every object under *prefix* and delete them. Idempotent."""
        keys = self._minio.list_objects(prefix)
        if not keys:
            return PurgeResult(deleted_count=0, failed_keys=[])
        failed = self._minio.delete_objects(keys)
        deleted = len(keys) - len(failed)
        if failed:
            logger.warning(
                "image_purge_partial",
                prefix=prefix,
                deleted=deleted,
                failed=len(failed),
                failed_keys=failed,
            )
        return PurgeResult(deleted_count=deleted, failed_keys=failed)

    # -- validation --------------------------------------------------------

    @staticmethod
    def validate_upload(content_type: str, data: bytes) -> tuple[int, int]:
        """Raise ValueError if the upload fails validation. Returns (width, height)."""
        if content_type not in ALLOWED_MIME_TYPES:
            raise ValueError(
                f"Unsupported MIME type '{content_type}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
            )
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError(
                f"File size {len(data)} exceeds maximum {MAX_UPLOAD_BYTES} bytes"
            )
        img = Image.open(BytesIO(data))
        w, h = img.size
        if w * h > MAX_PIXELS:
            raise ValueError(
                f"Image dimensions {w}x{h} ({w * h} px) exceed maximum {MAX_PIXELS} px"
            )
        return w, h

    # -- internal ----------------------------------------------------------

    def _render_one(self, img: Image.Image, spec: ImageVariantSpec) -> Image.Image:
        """Apply color convert + resize/fit + optional encode prep to a single variant."""
        # Colour conversion
        if spec.color_mode == "grayscale":
            img = img.convert("L")
        elif spec.color_mode == "bw_dither":
            img = img.convert("L").convert("1", dither=Image.Dither.FLOYDSTEINBERG)
        else:
            # rgb: ensure RGB (or RGBA for PNG)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")

        tw, th = spec.target_width, spec.target_height

        if spec.fit_mode == "cover":
            img = ImageOps.fit(img, (tw, th), method=Image.Resampling.LANCZOS)
        elif spec.fit_mode == "contain":
            img = ImageOps.contain(img, (tw, th), method=Image.Resampling.LANCZOS)
        elif spec.fit_mode == "pad":
            img = ImageOps.pad(img, (tw, th), color="#000000")

        return img


# -- helpers ---------------------------------------------------------------


def _find_slot(layout, slot_id: str):
    for s in layout.image_slots:
        if s.slot_id == slot_id:
            return s
    raise KeyError(f"Layout '{layout.id}' has no slot '{slot_id}'")


def _content_type_for(fmt: str) -> str:
    return {"webp": "image/webp", "jpeg": "image/jpeg", "png": "image/png"}.get(
        fmt, "image/png"
    )


def _pillow_format(fmt: str) -> str:
    return {"webp": "WEBP", "jpeg": "JPEG", "png": "PNG"}.get(fmt, "PNG")
