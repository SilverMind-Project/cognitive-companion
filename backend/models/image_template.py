from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class ImageTemplate(Base):
    """Template definition for e-ink display images with bounding-box regions."""

    __tablename__ = "image_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    width: Mapped[int] = mapped_column(Integer, default=800)
    height: Mapped[int] = mapped_column(Integer, default=480)
    image_filename: Mapped[str] = mapped_column(String(256))
    font_filename: Mapped[str] = mapped_column(
        String(256), default="NotoSansTamil-Regular.ttf"
    )
    regions_json: Mapped[list] = mapped_column(JSON, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
