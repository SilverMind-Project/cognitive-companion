"""REST API for knowledge documents and images.
Thin router: parse, call service, serialize.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from backend.core.auth import require_permission
from backend.core.database import get_db
from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.schemas.knowledge import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentImageOut,
    KnowledgeDocumentImageUpdate,
    KnowledgeDocumentListOut,
    KnowledgeDocumentOut,
    KnowledgeDocumentUpdate,
)
from backend.services.knowledge.ingestion_service import KnowledgeIngestionService

router = APIRouter(prefix="/knowledge/documents", tags=["knowledge"])


def _get_ingestion(request: Request) -> KnowledgeIngestionService:
    return request.app.state.knowledge_ingestion


def _add_presigned(img_row, minio_client) -> dict:
    d = {
        "id": img_row.id,
        "document_id": img_row.document_id,
        "minio_object_name": img_row.minio_object_name,
        "mime_type": img_row.mime_type,
        "width": img_row.width,
        "height": img_row.height,
        "alt_text": img_row.alt_text,
        "ord": img_row.ord,
    }
    try:
        d["presigned_url"] = minio_client.generate_presigned_url(
            img_row.minio_object_name, expiration=3600
        )
    except Exception:
        d["presigned_url"] = None
    return d


@router.post("", status_code=201)
async def create_document(
    request: Request,
    title: str = Form(...),
    source_text: str = Form(...),
    tags: str = Form(""),
    images: list[UploadFile] = File(default_factory=list),
    _auth: None = Depends(require_permission("POST /api/v1/knowledge/documents")),
):
    ingestion = _get_ingestion(request)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    created_by = request.state.auth_context.name if hasattr(request.state, "auth_context") else "caregiver"
    doc = await ingestion.create_document(
        title=title,
        source_text=source_text,
        tags=tag_list,
        created_by=created_by,
        images=images,
    )
    minio = request.app.state.minio_client
    return _doc_out(doc, minio)


@router.get("")
async def list_documents(
    request: Request,
    status: str | None = Query(None),
    tag: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _auth: None = Depends(require_permission("GET /api/v1/knowledge/documents")),
):
    ingestion = _get_ingestion(request)
    docs, total = ingestion.list_documents(status=status, tag=tag, q=q, limit=limit, offset=offset)
    return {
        "items": [
            KnowledgeDocumentListOut.model_validate(_doc_list_out(d, request.app.state.minio_client))
            for d in docs
        ],
        "total": total,
    }


@router.get("/{doc_id}")
async def get_document(
    doc_id: int,
    request: Request,
    _auth: None = Depends(require_permission("GET /api/v1/knowledge/documents")),
):
    ingestion = _get_ingestion(request)
    doc = ingestion.get_document(doc_id)
    if doc is None:
        raise NotFoundError(f"Knowledge document {doc_id} not found")
    return _doc_out(doc, request.app.state.minio_client)


@router.patch("/{doc_id}")
async def update_document(
    doc_id: int,
    body: KnowledgeDocumentUpdate,
    request: Request,
    _auth: None = Depends(require_permission("PATCH /api/v1/knowledge/documents")),
):
    ingestion = _get_ingestion(request)
    doc = await ingestion.update_document(doc_id, **body.model_dump(exclude_none=True))
    return _doc_out(doc, request.app.state.minio_client)


# -- state transitions -------------------------------------------------------


@router.post("/{doc_id}/approve")
async def approve_document(
    doc_id: int,
    request: Request,
    _auth: None = Depends(require_permission("POST /api/v1/knowledge/documents")),
):
    ingestion = _get_ingestion(request)
    doc = ingestion.approve_document(doc_id)
    return _doc_out(doc, request.app.state.minio_client)


@router.post("/{doc_id}/archive")
async def archive_document(
    doc_id: int,
    request: Request,
    _auth: None = Depends(require_permission("POST /api/v1/knowledge/documents")),
):
    ingestion = _get_ingestion(request)
    doc = ingestion.archive_document(doc_id)
    return _doc_out(doc, request.app.state.minio_client)


@router.post("/{doc_id}/restore")
async def restore_document(
    doc_id: int,
    request: Request,
    _auth: None = Depends(require_permission("POST /api/v1/knowledge/documents")),
):
    ingestion = _get_ingestion(request)
    doc = ingestion.restore_document(doc_id)
    return _doc_out(doc, request.app.state.minio_client)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: int,
    request: Request,
    _auth: None = Depends(require_permission("DELETE /api/v1/knowledge/documents")),
):
    ingestion = _get_ingestion(request)
    minio = request.app.state.minio_client
    try:
        ingestion.delete_document(doc_id)
    except NotFoundError as e:
        raise e
    # Purge MinIO prefix after successful DB delete
    from backend.services.knowledge.image_pipeline import ImagePipeline  # local to avoid circular import
    pipeline = request.app.state.image_pipeline
    await pipeline.purge_prefix(f"knowledge/{doc_id}/")


@router.post("/{doc_id}/reembed")
async def reembed_document(
    doc_id: int,
    request: Request,
    _auth: None = Depends(require_permission("POST /api/v1/knowledge/documents")),
):
    """Force re-chunk and re-embed a document. Resets status to uploaded first."""
    ingestion = _get_ingestion(request)
    doc = ingestion.get_document(doc_id)
    if doc is None:
        raise NotFoundError(f"Knowledge document {doc_id} not found")

    # Reset to uploaded and re-chunk (update_document handles _chunk_and_embed internally)
    updated = await ingestion.update_document(doc_id, source_text=doc.source_text)
    return _doc_out(updated, request.app.state.minio_client)


# -- document images ---------------------------------------------------------


@router.post("/{doc_id}/images", status_code=201)
async def add_document_image(
    doc_id: int,
    request: Request,
    file: UploadFile = File(...),
    alt_text: str = Form(""),
    ord: int | None = Form(None),
    _auth: None = Depends(require_permission("POST /api/v1/knowledge/documents")),
):
    ingestion = _get_ingestion(request)
    img_row = await ingestion.add_image(doc_id, file, alt_text=alt_text, ord=ord)
    return _add_presigned(img_row, request.app.state.minio_client)


@router.patch("/{doc_id}/images/{img_id}")
async def update_document_image(
    doc_id: int,
    img_id: int,
    body: KnowledgeDocumentImageUpdate,
    request: Request,
    _auth: None = Depends(require_permission("PATCH /api/v1/knowledge/documents")),
):
    ingestion = _get_ingestion(request)
    img_row = ingestion.update_image(img_id, **body.model_dump(exclude_none=True))
    return _add_presigned(img_row, request.app.state.minio_client)


@router.delete("/{doc_id}/images/{img_id}", status_code=204)
async def delete_document_image(
    doc_id: int,
    img_id: int,
    request: Request,
    _auth: None = Depends(require_permission("DELETE /api/v1/knowledge/documents")),
):
    ingestion = _get_ingestion(request)
    await ingestion.delete_image(img_id)


# -- serialisers ------------------------------------------------------------


def _doc_out(doc, minio_client) -> dict[str, Any]:
    return {
        "id": doc.id,
        "title": doc.title,
        "source_text": doc.source_text,
        "tags": doc.tags or [],
        "status": doc.status,
        "created_by": doc.created_by,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        "archived_at": doc.archived_at.isoformat() if doc.archived_at else None,
        "images": [_add_presigned(img, minio_client) for img in (doc.images or [])],
        "chunk_count": len(doc.chunks) if doc.chunks else 0,
    }


def _doc_list_out(doc, minio_client) -> dict[str, Any]:
    return {
        "id": doc.id,
        "title": doc.title,
        "tags": doc.tags or [],
        "status": doc.status,
        "created_by": doc.created_by,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        "image_count": len(doc.images) if doc.images else 0,
    }
