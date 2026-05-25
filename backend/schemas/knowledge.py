"""Pydantic v2 wire models for knowledge documents and images."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.schemas.common import OptionalUTCDatetime, OutSchema, UTCDatetime

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


class KnowledgeDocumentImageOut(OutSchema):
    id: int
    document_id: int
    minio_object_name: str
    mime_type: str
    width: int | None = None
    height: int | None = None
    alt_text: str = ""
    ord: int = 0
    presigned_url: str | None = None


class KnowledgeDocumentOut(OutSchema):
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


class KnowledgeDocumentListOut(OutSchema):
    id: int
    title: str
    tags: list[str] = []
    status: str
    created_by: str
    created_at: UTCDatetime
    updated_at: UTCDatetime
    image_count: int = 0


# -- Knowledge Document Image -------------------------------------------------


class KnowledgeDocumentImageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alt_text: str | None = None
    ord: int | None = None
