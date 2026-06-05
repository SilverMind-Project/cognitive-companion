"""Internal integration for rendering text onto e-ink display templates.

Unlike external integration clients, this one operates locally via PIL.
Called by NotificationDispatcher (for alert-triggered rendering) and
directly by the image router or pipeline executor.
"""

from __future__ import annotations

import textwrap
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.models.image_state import ActiveImageState
from backend.models.image_template import ImageTemplate
from backend.models.sensor import Sensor

logger = get_logger(__name__)

_TEMPLATE_PREFIX = "eink/templates"
_ACTIVE_PREFIX = "eink/active"


class EInkRenderer:
    """PIL-based renderer for e-ink display images backed by MinIO."""

    def __init__(
        self,
        db_session_factory: Callable[[], Session],
        minio_client: MinioClient,
    ) -> None:
        self._db_factory = db_session_factory
        self._minio = minio_client

        _backend_dir = Path(__file__).resolve().parents[1]

        self._fonts_dir = Path(settings.as_str("image.font_dir", allow_empty=False))
        self._default_font = settings.as_str("image.default_font", allow_empty=False)
        self._default_template = settings.as_str("image.default_template", allow_empty=False)
        self._default_expiry = settings.as_int("image.default_expiry_minutes")
        self._display_width = settings.as_int("image.display_width")
        self._display_height = settings.as_int("image.display_height")

        # Template dir is only used for seeding at startup; not accessed at render time.
        self._local_templates_dir = Path(
            settings.as_str("image.template_dir", allow_empty=False)
        )

    # ------------------------------------------------------------------
    # Key helpers
    # ------------------------------------------------------------------

    def get_active_image_key(self, sensor_id: str) -> str:
        return f"{_ACTIVE_PREFIX}/{sensor_id}.png"

    def get_template_key(self, filename: str) -> str:
        return f"{_TEMPLATE_PREFIX}/{filename}"

    # ------------------------------------------------------------------
    # Startup seed
    # ------------------------------------------------------------------

    def seed_templates(self) -> None:
        """Upload bundled template PNGs to MinIO if they are not already there.

        Idempotent: checks existing keys first and skips files that are
        already present.  Called once during app lifespan startup so that
        the default template fallback and any checked-in templates are
        available immediately after a fresh deployment.
        """
        if not self._local_templates_dir.exists():
            return

        existing = set(self._minio.list_objects(_TEMPLATE_PREFIX))
        for png_file in sorted(self._local_templates_dir.glob("*.png")):
            key = self.get_template_key(png_file.name)
            if key not in existing:
                self._minio.upload_bytes(png_file.read_bytes(), key, "image/png")
                logger.info("eink_template_seeded", key=key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def render(
        self,
        text: str,
        template: str | None = "alert",
        template_id: int | None = None,
        sensor_ids: list[str] | None = None,
        expires_in_minutes: int = 30,
        region_name: str | None = None,
        overlay_image: bytes | None = None,
    ) -> list[str]:
        """Render text onto a template and upload as active image for target devices.

        Returns list of sensor_ids that were rendered to.
        """
        db = self._db_factory()
        try:
            template_bytes, regions, font_path = self._resolve_template(template, template_id, db)
            resolved_template_id = template_id
            targets = self._resolve_sensor_ids(sensor_ids, db)

            if not targets:
                logger.warning("eink_render_no_targets")
                return []

            img = self._render_image(
                text, template_bytes, regions, font_path, region_name, overlay_image
            )

            buf = BytesIO()
            img.save(buf, "PNG")
            png_bytes = buf.getvalue()

            for sid in targets:
                self._minio.upload_bytes(png_bytes, self.get_active_image_key(sid), "image/png")
                self._upsert_image_state(sid, resolved_template_id, text, expires_in_minutes, db)

            db.commit()
            logger.info(
                "eink_rendered",
                sensor_ids=targets,
                template=template,
                template_id=template_id,
            )
            return targets
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def render_preview(
        self,
        text: str,
        template_id: int | None = None,
        template_name: str | None = "alert",
        region_name: str | None = None,
    ) -> bytes:
        """Render and return PNG bytes without saving to MinIO."""
        db = self._db_factory()
        try:
            template_bytes, regions, font_path = self._resolve_template(
                template_name, template_id, db
            )
            img = self._render_image(text, template_bytes, regions, font_path, region_name)
            buf = BytesIO()
            img.save(buf, "PNG")
            return buf.getvalue()
        finally:
            db.close()

    def render_preview_inline(
        self,
        text: str,
        image_bytes: bytes,
        regions: list[dict],
        font_filename: str,
    ) -> bytes:
        """Render text onto provided raw image bytes (no DB or MinIO lookup needed)."""
        img: Image.Image = Image.open(BytesIO(image_bytes))
        img = img.resize((self._display_width, self._display_height), Image.Resampling.LANCZOS)
        img = img.convert("RGBA")
        font_path = self._fonts_dir / font_filename
        if not font_path.exists():
            font_path = self._fonts_dir / self._default_font
        result = self._render_image(text, img, regions or [], font_path)
        buf = BytesIO()
        result.save(buf, "PNG")
        return buf.getvalue()

    def render_preview_with_overrides(
        self,
        text: str,
        template_id: int,
        regions_override: list[dict] | None = None,
        font_filename_override: str | None = None,
    ) -> bytes:
        """Render preview using an existing template with optional region/font overrides."""
        db = self._db_factory()
        try:
            template_bytes, regions, font_path = self._resolve_template(None, template_id, db)
            if regions_override is not None:
                regions = regions_override
            if font_filename_override:
                candidate = self._fonts_dir / font_filename_override
                if candidate.exists():
                    font_path = candidate
            result = self._render_image(text, template_bytes, regions, font_path)
            buf = BytesIO()
            result.save(buf, "PNG")
            return buf.getvalue()
        finally:
            db.close()

    async def reset(self, sensor_ids: list[str] | None = None) -> list[str]:
        """Reset active images to default template for given sensors (or all)."""
        db = self._db_factory()
        try:
            targets = self._resolve_sensor_ids(sensor_ids, db)
            default_bytes = self._minio.get_object(
                self.get_template_key(f"{self._default_template}.png")
            )

            for sid in targets:
                active_key = self.get_active_image_key(sid)
                if default_bytes is not None:
                    self._minio.upload_bytes(default_bytes, active_key, "image/png")
                else:
                    try:
                        self._minio.delete_object(active_key)
                    except Exception:
                        logger.warning("eink_reset_delete_failed", sensor_id=sid)

                state = db.execute(
                    select(ActiveImageState).where(ActiveImageState.sensor_id == sid)
                ).scalar_one_or_none()
                if state:
                    state.expires_at = None
                    state.rendered_text = None
                    state.template_id = None

            db.commit()
            logger.info("eink_reset", sensor_ids=targets)
            return targets
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render_image(
        self,
        text: str,
        template: bytes | None | Image.Image,
        regions: list[dict],
        font_path: Path,
        region_name: str | None = None,
        overlay_image: bytes | None = None,
    ) -> Image.Image:
        """Core PIL rendering logic.

        template can be:
        - bytes: PNG/image bytes fetched from MinIO
        - Image.Image: already-loaded PIL image (from render_preview_inline)
        - None: no template available; renders onto a white canvas
        """
        if isinstance(template, bytes):
            img = Image.open(BytesIO(template)).copy()
        elif template is None:
            img = Image.new(
                "RGB",
                (self._display_width, self._display_height),
                color=(255, 255, 255),
            )
        else:
            img = template.copy()

        draw = ImageDraw.Draw(img, "RGBA")
        img_width, img_height = img.size

        if not regions:
            pad_x = int(img_width * 0.1)
            pad_y = int(img_height * 0.15)
            regions = [
                {
                    "name": "main_text",
                    "x": pad_x,
                    "y": pad_y,
                    "width": img_width - 2 * pad_x,
                    "height": img_height - 2 * pad_y,
                    "font_size_max": 48,
                    "font_size_min": 12,
                    "align": "center",
                    "bg_color": [0, 0, 0, 160],
                    "text_color": [255, 255, 255, 255],
                }
            ]

        if region_name:
            regions = [r for r in regions if r.get("name") == region_name]
            if not regions:
                regions = [regions[0]] if regions else []

        for region in regions:
            if region.get("type") == "image" and overlay_image:
                self._render_image_region(img, overlay_image, region)
            else:
                self._render_region(draw, text, region, font_path)

        return img.convert("RGB")

    def _wrap_text(self, text: str, chars_per_line: int, multiline: bool) -> list[str]:
        if multiline:
            result: list[str] = []
            for para in text.split("\n"):
                if para.strip():
                    result.extend(textwrap.wrap(para, width=chars_per_line))
                else:
                    result.append("")
            return result or [""]
        else:
            return textwrap.wrap(text.replace("\n", " "), width=chars_per_line) or [text]

    def _render_region(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        region: dict,
        font_path: Path,
    ) -> None:
        bx = region.get("x", 0)
        by = region.get("y", 0)
        bw = region.get("width", 640)
        bh = region.get("height", 336)
        font_size_max = region.get("font_size_max", 48)
        font_size_min = region.get("font_size_min", 12)
        align = region.get("align", "center")
        bg_color = tuple(region.get("bg_color", [0, 0, 0, 160]))
        text_color = tuple(region.get("text_color", [255, 255, 255, 255]))
        multiline = region.get("multiline", True)

        font_size = font_size_max
        font = None
        lines: list[str] = [text]
        line_height = font_size * 1.3

        while font_size >= font_size_min:
            try:
                font = ImageFont.truetype(str(font_path), font_size)
            except OSError:
                font = ImageFont.load_default()  # type: ignore[assignment]
                break

            avg_char_width = font_size * 0.6
            chars_per_line = max(1, int(bw / avg_char_width))
            lines = self._wrap_text(text, chars_per_line, multiline)

            line_height = font_size * 1.3
            total_height = line_height * len(lines)

            if total_height <= bh:
                break
            font_size -= 2

        if font is None:
            font = ImageFont.load_default()  # type: ignore[assignment]

        avg_char_width = font_size * 0.6
        chars_per_line = max(1, int(bw / avg_char_width))
        lines = self._wrap_text(text, chars_per_line, multiline)
        line_height = font_size * 1.3
        total_height = line_height * len(lines)

        if len(bg_color) < 4 or bg_color[3] > 0:
            bg_margin = 10
            draw.rectangle(
                [bx - bg_margin, by - bg_margin, bx + bw + bg_margin, by + bh + bg_margin],
                fill=bg_color,
            )

        y_start = by + (bh - total_height) / 2
        for i, line in enumerate(lines):
            line_bbox = draw.textbbox((0, 0), line, font=font)
            line_width = line_bbox[2] - line_bbox[0]
            if align == "center":
                x = bx + (bw - line_width) / 2
            elif align == "right":
                x = bx + bw - line_width
            else:
                x = bx
            y = y_start + i * line_height
            draw.text((x, y), line, fill=text_color, font=font)

    @staticmethod
    def _render_image_region(
        img: Image.Image,
        overlay_bytes: bytes,
        region: dict,
    ) -> None:
        bx = region.get("x", 0)
        by = region.get("y", 0)
        bw = region.get("width", 760)
        bh = region.get("height", 260)
        try:
            overlay = Image.open(BytesIO(overlay_bytes)).convert("RGBA")
            overlay = overlay.resize((bw, bh), Image.Resampling.LANCZOS)
            img.paste(overlay, (bx, by), overlay)
        except Exception:
            logger.exception("eink_image_region_render_failed")

    def _resolve_template(
        self,
        template_name: str | None,
        template_id: int | None,
        db: Session,
    ) -> tuple[bytes | None, list[dict], Path]:
        """Resolve template to (image_bytes_or_None, regions, font_path).

        Returns None for image bytes when the template is not found in MinIO;
        _render_image will paint a white canvas in that case.
        """
        if template_id is not None:
            tmpl = db.execute(
                select(ImageTemplate).where(ImageTemplate.id == template_id)
            ).scalar_one_or_none()
            if tmpl:
                img_bytes = self._minio.get_object(self.get_template_key(tmpl.image_filename))
                return img_bytes, tmpl.regions_json or [], self._fonts_dir / tmpl.font_filename

        name = template_name or self._default_template
        db_tmpl = db.execute(
            select(ImageTemplate).where(ImageTemplate.name == name)
        ).scalar_one_or_none()
        if db_tmpl:
            img_bytes = self._minio.get_object(self.get_template_key(db_tmpl.image_filename))
            return img_bytes, db_tmpl.regions_json or [], self._fonts_dir / db_tmpl.font_filename

        # Pure MinIO fallback by name — no regions, default font
        img_bytes = self._minio.get_object(f"{_TEMPLATE_PREFIX}/{name}.png")
        return img_bytes, [], self._fonts_dir / self._default_font

    def _resolve_sensor_ids(self, sensor_ids: list[str] | None, db: Session) -> list[str]:
        if sensor_ids:
            return sensor_ids

        default_targets = settings.section("notifications.eink").as_list("default_targets")
        if default_targets:
            return default_targets

        sensors = (
            db.execute(
                select(Sensor.id).where(
                    Sensor.sensor_type == "eink",
                    Sensor.enabled == True,  # noqa: E712
                )
            )
            .scalars()
            .all()
        )
        return list(sensors) if sensors else []

    def _upsert_image_state(
        self,
        sensor_id: str,
        template_id: int | None,
        text: str,
        expires_minutes: int,
        db: Session,
    ) -> None:
        expires_at = datetime.now(UTC) + timedelta(minutes=expires_minutes)
        state = db.execute(
            select(ActiveImageState).where(ActiveImageState.sensor_id == sensor_id)
        ).scalar_one_or_none()

        if state:
            state.template_id = template_id
            state.rendered_text = text
            state.expires_at = expires_at
        else:
            state = ActiveImageState(
                sensor_id=sensor_id,
                template_id=template_id,
                rendered_text=text,
                expires_at=expires_at,
            )
            db.add(state)
