"""REST API for knowledge documents and images.
Thin router: parse, call service, serialize.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

from backend.core.auth import AuthContext, actor_from_auth, require_permission
from backend.core.exceptions import NotFoundError
from backend.routers.dependencies import get_knowledge_ingestion
from backend.schemas.knowledge import (
    KnowledgeDocumentImageOut,
    KnowledgeDocumentImageUpdate,
    KnowledgeDocumentListOut,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentOut,
    KnowledgeDocumentUpdate,
)
from backend.services.knowledge.ingestion_service import KnowledgeIngestionService

router = APIRouter(prefix="/knowledge/documents", tags=["knowledge"])


def _add_presigned(img_row: Any, minio_client: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
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
    except Exception:  # noqa: BLE001 - optional presigned URL enrichment
        d["presigned_url"] = None
    return d


@router.post("", status_code=201, response_model=KnowledgeDocumentOut)
async def create_document(
    request: Request,
    title: str = Form(...),
    source_text: str = Form(...),
    tags: str = Form(""),
    images: list[UploadFile] = File(default_factory=list),
    ingestion: KnowledgeIngestionService = Depends(get_knowledge_ingestion),
    auth: AuthContext = Depends(require_permission("knowledge.documents:write")),
) -> dict[str, Any]:
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    doc = await ingestion.create_document(
        title=title,
        source_text=source_text,
        tags=tag_list,
        created_by=actor_from_auth(auth),
        images=images,
    )
    return _doc_out(doc, request.app.state.minio_client)


@router.get("", response_model=KnowledgeDocumentListResponse)
async def list_documents(
    request: Request,
    status: str | None = Query(None),
    tag: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ingestion: KnowledgeIngestionService = Depends(get_knowledge_ingestion),
    _auth: None = Depends(require_permission("knowledge.documents:read")),
) -> dict[str, Any]:
    docs, total = ingestion.list_documents(status=status, tag=tag, q=q, limit=limit, offset=offset)
    return {
        "items": [
            KnowledgeDocumentListOut.model_validate(
                _doc_list_out(d, request.app.state.minio_client)
            )
            for d in docs
        ],
        "total": total,
    }


@router.get("/{doc_id}", response_model=KnowledgeDocumentOut)
async def get_document(
    doc_id: int,
    request: Request,
    ingestion: KnowledgeIngestionService = Depends(get_knowledge_ingestion),
    _auth: None = Depends(require_permission("knowledge.documents:read")),
) -> dict[str, Any]:
    doc = ingestion.get_document(doc_id)
    if doc is None:
        raise NotFoundError("Knowledge document", doc_id)
    return _doc_out(doc, request.app.state.minio_client)


@router.patch("/{doc_id}", response_model=KnowledgeDocumentOut)
async def update_document(
    doc_id: int,
    body: KnowledgeDocumentUpdate,
    request: Request,
    ingestion: KnowledgeIngestionService = Depends(get_knowledge_ingestion),
    _auth: None = Depends(require_permission("knowledge.documents:write")),
) -> dict[str, Any]:
    doc = await ingestion.update_document(doc_id, **body.model_dump(exclude_none=True))
    return _doc_out(doc, request.app.state.minio_client)


# -- state transitions -------------------------------------------------------


@router.post("/{doc_id}/approve", response_model=KnowledgeDocumentOut)
async def approve_document(
    doc_id: int,
    request: Request,
    ingestion: KnowledgeIngestionService = Depends(get_knowledge_ingestion),
    _auth: None = Depends(require_permission("knowledge.documents:write")),
) -> dict[str, Any]:
    doc = ingestion.approve_document(doc_id)
    return _doc_out(doc, request.app.state.minio_client)


@router.post("/{doc_id}/archive", response_model=KnowledgeDocumentOut)
async def archive_document(
    doc_id: int,
    request: Request,
    ingestion: KnowledgeIngestionService = Depends(get_knowledge_ingestion),
    _auth: None = Depends(require_permission("knowledge.documents:write")),
) -> dict[str, Any]:
    doc = ingestion.archive_document(doc_id)
    return _doc_out(doc, request.app.state.minio_client)


@router.post("/{doc_id}/restore", response_model=KnowledgeDocumentOut)
async def restore_document(
    doc_id: int,
    request: Request,
    ingestion: KnowledgeIngestionService = Depends(get_knowledge_ingestion),
    _auth: None = Depends(require_permission("knowledge.documents:write")),
) -> dict[str, Any]:
    doc = ingestion.restore_document(doc_id)
    return _doc_out(doc, request.app.state.minio_client)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: int,
    ingestion: KnowledgeIngestionService = Depends(get_knowledge_ingestion),
    _auth: None = Depends(require_permission("knowledge.documents:delete")),
) -> None:
    await ingestion.delete_document(doc_id)


@router.post("/{doc_id}/reembed", response_model=KnowledgeDocumentOut)
async def reembed_document(
    doc_id: int,
    request: Request,
    ingestion: KnowledgeIngestionService = Depends(get_knowledge_ingestion),
    _auth: None = Depends(require_permission("knowledge.documents:write")),
) -> dict[str, Any]:
    """Re-chunk and re-embed unchanged content; an approved document stays approved."""
    doc = await ingestion.reembed_document(doc_id)
    return _doc_out(doc, request.app.state.minio_client)


# -- document images ---------------------------------------------------------


@router.post("/{doc_id}/images", status_code=201, response_model=KnowledgeDocumentImageOut)
async def add_document_image(
    doc_id: int,
    request: Request,
    file: UploadFile = File(...),
    alt_text: str = Form(""),
    ord: int | None = Form(None),
    ingestion: KnowledgeIngestionService = Depends(get_knowledge_ingestion),
    _auth: None = Depends(require_permission("knowledge.documents:write")),
) -> dict[str, Any]:
    img_row = await ingestion.add_image(doc_id, file, alt_text=alt_text, ord=ord)
    return _add_presigned(img_row, request.app.state.minio_client)


@router.patch("/{doc_id}/images/{img_id}", response_model=KnowledgeDocumentImageOut)
async def update_document_image(
    doc_id: int,
    img_id: int,
    body: KnowledgeDocumentImageUpdate,
    request: Request,
    ingestion: KnowledgeIngestionService = Depends(get_knowledge_ingestion),
    _auth: None = Depends(require_permission("knowledge.documents:write")),
) -> dict[str, Any]:
    _ = doc_id
    img_row = ingestion.update_image(img_id, **body.model_dump(exclude_none=True))
    return _add_presigned(img_row, request.app.state.minio_client)


@router.delete("/{doc_id}/images/{img_id}", status_code=204)
async def delete_document_image(
    doc_id: int,
    img_id: int,
    ingestion: KnowledgeIngestionService = Depends(get_knowledge_ingestion),
    _auth: None = Depends(require_permission("knowledge.documents:delete")),
) -> None:
    _ = doc_id
    await ingestion.delete_image(img_id)


# -- serialisers ------------------------------------------------------------


def _doc_out(doc: Any, minio_client: Any) -> dict[str, Any]:
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


def _doc_list_out(doc: Any, minio_client: Any) -> dict[str, Any]:
    _ = minio_client
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
