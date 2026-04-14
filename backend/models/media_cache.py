from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.core.time import UTCDateTime


class MediaCache(Base):
    """Tracks MinIO objects for delayed deletion and reverse-chronological access."""

    __tablename__ = "media_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_name: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    presigned_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sensor_id: Mapped[str | None] = mapped_column(String(128), index=True)
    captured_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
