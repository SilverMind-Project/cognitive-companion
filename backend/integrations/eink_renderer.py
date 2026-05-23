"""Internal integration for rendering text onto e-ink display templates.

Unlike external integration clients, this one operates locally via PIL.
Called by NotificationDispatcher (for alert-triggered rendering) and
directly by the image router or pipeline executor.
"""

from __future__ import annotations

import shutil
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
from backend.models.image_state import ActiveImageState
from backend.models.image_template import ImageTemplate
from backend.models.sensor import Sensor

logger = get_logger(__name__)


class EInkRenderer:
    """PIL-based renderer for e-ink display images."""

    def __init__(self, db_session_factory: Callable[[], Session]) -> None:
        self._db_factory = db_session_factory

        _backend_dir = Path(__file__).resolve().parents[1]

        # Read paths from settings.yaml, fall back to defaults
        template_dir = settings.as_str("image.template_dir")
        output_dir = settings.as_str("image.output_dir")
        font_dir = settings.as_str("image.font_dir")

        self._templates_dir = (
            Path(template_dir) if template_dir else _backend_dir / "assets" / "images" / "templates"
        )
        self._images_dir = Path(output_dir) if output_dir else _backend_dir / "assets" / "images"
        self._fonts_dir = Path(font_dir) if font_dir else _backend_dir / "assets" / "fonts"
        self._default_font = settings.as_str("image.default_font")
        self._default_template = settings.as_str("image.default_template")
        self._default_expiry = settings.as_int("image.default_expiry_minutes")
        self._display_width = settings.as_int("image.display_width")
        self._display_height = settings.as_int("image.display_height")

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
        """Render text onto a template and save as active image for target devices.

        Returns list of sensor_ids that were rendered to.
        """
        db = self._db_factory()
        try:
            template_path, regions, font_path = self._resolve_template(template, template_id, db)
            resolved_template_id = template_id
            targets = self._resolve_sensor_ids(sensor_ids, db)

            if not targets:
                logger.warning("eink_render_no_targets")
                return []

            img = self._render_image(
                text, template_path, regions, font_path, region_name, overlay_image
            )

            self._images_dir.mkdir(parents=True, exist_ok=True)
            for sid in targets:
                out_path = self.get_active_image_path(sid)
                img.save(out_path, "PNG")
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
        """Render and return PNG bytes without saving to disk."""
        db = self._db_factory()
        try:
            template_path, regions, font_path = self._resolve_template(
                template_name, template_id, db
            )
            img = self._render_image(text, template_path, regions, font_path, region_name)
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
        """Render text onto provided raw image bytes (no DB lookup needed)."""
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
        """Render preview using an existing template's image with optional region/font overrides."""
        db = self._db_factory()
        try:
            template_path, regions, font_path = self._resolve_template(None, template_id, db)
            if regions_override is not None:
                regions = regions_override
            if font_filename_override:
                candidate = self._fonts_dir / font_filename_override
                if candidate.exists():
                    font_path = candidate
            result = self._render_image(text, template_path, regions, font_path)
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
            default_path = self._templates_dir / f"{self._default_template}.png"

            for sid in targets:
                out_path = self.get_active_image_path(sid)
                if default_path.exists():
                    shutil.copy2(default_path, out_path)
                elif out_path.exists():
                    out_path.unlink()

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

    def get_active_image_path(self, sensor_id: str) -> Path:
        """Return the path to the active image for a sensor."""
        return self._images_dir / f"active_{sensor_id}.png"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render_image(
        self,
        text: str,
        template: Path | Image.Image,
        regions: list[dict],
        font_path: Path,
        region_name: str | None = None,
        overlay_image: bytes | None = None,
    ):
        """Core PIL rendering logic — renders text and optional image into regions.

        template can be a filesystem Path or an already-loaded PIL Image.
        """
        if isinstance(template, Path):
            if not template.exists():
                default_path = self._templates_dir / f"{self._default_template}.png"
                template = default_path if default_path.exists() else template
            img = Image.open(template).copy()
        else:
            img = template.copy()

        draw = ImageDraw.Draw(img, "RGBA")
        img_width, img_height = img.size

        # If no regions defined, use a default centered bounding box
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

        # Filter to target region if specified
        if region_name:
            regions = [r for r in regions if r.get("name") == region_name]
            if not regions:
                regions = [regions[0]] if regions else []

        for region in regions:
            if region.get("type") == "image" and overlay_image:
                self._render_image_region(img, overlay_image, region)
            else:
                self._render_region(draw, text, region, font_path)

        # Convert to RGB (eInk doesn't need alpha)
        return img.convert("RGB")

    def _wrap_text(self, text: str, chars_per_line: int, multiline: bool) -> list[str]:
        """Wrap text into lines, optionally respecting explicit newlines."""
        if multiline:
            # Split on explicit newlines first, then word-wrap each paragraph
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
        draw,
        text: str,
        region: dict,
        font_path: Path,
    ) -> None:
        """Render text into a single bounding-box region."""
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

        # Find the best font size to fit the bounding box
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

        # Re-wrap with final font size
        avg_char_width = font_size * 0.6
        chars_per_line = max(1, int(bw / avg_char_width))
        lines = self._wrap_text(text, chars_per_line, multiline)
        line_height = font_size * 1.3
        total_height = line_height * len(lines)

        # Draw background only if not fully transparent
        if len(bg_color) < 4 or bg_color[3] > 0:
            bg_margin = 10
            draw.rectangle(
                [bx - bg_margin, by - bg_margin, bx + bw + bg_margin, by + bh + bg_margin],
                fill=bg_color,
            )

        # Draw text lines
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
        """Composite a content image into a template image region."""
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
    ) -> tuple[Path, list[dict], Path]:
        """Resolve template to (image_path, regions, font_path)."""
        if template_id is not None:
            tmpl = db.execute(
                select(ImageTemplate).where(ImageTemplate.id == template_id)
            ).scalar_one_or_none()
            if tmpl:
                return (
                    self._templates_dir / tmpl.image_filename,
                    tmpl.regions_json or [],
                    self._fonts_dir / tmpl.font_filename,
                )

        # Filesystem fallback by name
        name = template_name or self._default_template
        template_path = self._templates_dir / f"{name}.png"

        # Check if there's a DB template with this name (for region definitions)
        db_tmpl = db.execute(
            select(ImageTemplate).where(ImageTemplate.name == name)
        ).scalar_one_or_none()
        if db_tmpl:
            return (
                self._templates_dir / db_tmpl.image_filename,
                db_tmpl.regions_json or [],
                self._fonts_dir / db_tmpl.font_filename,
            )

        # Pure filesystem fallback  no regions, default font
        font_path = self._fonts_dir / self._default_font
        if not font_path.exists():
            font_path = self._fonts_dir / "NotoSans-Regular.ttf"
        return template_path, [], font_path

    def _resolve_sensor_ids(self, sensor_ids: list[str] | None, db: Session) -> list[str]:
        """Resolve target sensor IDs. None = all enabled eink sensors."""
        if sensor_ids:
            return sensor_ids

        # Check notification config for default targets
        default_targets = settings.section("notifications.eink").as_list("default_targets")
        if default_targets:
            return default_targets

        # Fall back to all eink-type sensors
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
        """Insert or update ActiveImageState for the given sensor_id."""
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
