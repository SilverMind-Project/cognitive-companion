"""Pydantic v2 wire models for knowledge documents and images."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.common import OptionalUTCDatetime, UTCDatetime


# -- Knowledge Document -------------------------------------------------------


class KnowledgeDocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    source_text: str
    tags: list[str] = []


class KnowledgeDocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    source_text: str | None = None
    tags: list[str] | None = None


class KnowledgeDocumentImageOut(BaseModel):
    id: int
    document_id: int
    minio_object_name: str
    mime_type: str
    width: int | None = None
    height: int | None = None
    alt_text: str = ""
    ord: int = 0
    presigned_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class KnowledgeDocumentOut(BaseModel):
    id: int
    title: str
    source_text: str
    tags: list[str] = []
    status: str
    created_by: str
    created_at: UTCDatetime
    updated_at: UTCDatetime
    archived_at: OptionalUTCDatetime = None
    images: list[KnowledgeDocumentImageOut] = []
    chunk_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class KnowledgeDocumentListOut(BaseModel):
    id: int
    title: str
    tags: list[str] = []
    status: str
    created_by: str
    created_at: UTCDatetime
    updated_at: UTCDatetime
    image_count: int = 0

    model_config = ConfigDict(from_attributes=True)


# -- Knowledge Document Image -------------------------------------------------


class KnowledgeDocumentImageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alt_text: str | None = None
    ord: int | None = None
