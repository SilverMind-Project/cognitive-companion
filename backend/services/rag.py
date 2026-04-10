"""
Simple RAG (Retrieval-Augmented Generation) lookup service.

Provides contextual information from a local document index to enrich
the assistant's responses when a senior asks questions. Falls back
gracefully if no index is configured.

This is a lightweight implementation using TF-IDF for text matching.
Can be swapped for FAISS/ChromaDB by overriding the ``lookup`` method.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class RAGService:
    """Simple text-based retrieval service."""

    def __init__(self) -> None:
        self.enabled = settings.get("rag.enabled", False)
        self.index_path = Path(settings.get("rag.index_path", "data/rag_index"))
        self.threshold = settings.get("rag.threshold", 0.7)
        self.max_results = settings.get("rag.max_results", 5)
        self._documents: list[dict[str, Any]] = []
        self._loaded = False

    def load(self) -> None:
        """Load documents from the index directory."""
        if not self.enabled:
            return

        docs_file = self.index_path / "documents.json"
        if not docs_file.exists():
            logger.info("rag_no_index_found", path=str(docs_file))
            return

        try:
            with open(docs_file) as f:
                self._documents = json.load(f)
            self._loaded = True
            logger.info("rag_loaded", count=len(self._documents))
        except Exception:
            logger.exception("rag_load_error")

    def lookup(self, query: str) -> str:
        """Look up relevant context for a query.

        Returns a context string or empty string if nothing relevant found.
        """
        if not self.enabled or not self._loaded or not self._documents:
            return ""

        # Simple keyword matching (production: replace with embedding similarity)
        query_words = set(query.lower().split())
        scored: list[tuple[float, str]] = []

        for doc in self._documents:
            content = doc.get("content", "")
            doc_words = set(content.lower().split())
            if not doc_words:
                continue
            overlap = len(query_words & doc_words)
            score = overlap / max(len(query_words), 1)
            if score >= self.threshold:
                scored.append((score, content))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [text for _, text in scored[: self.max_results]]

        if results:
            return "\n---\n".join(results)
        return ""

    def add_document(self, content: str, metadata: dict[str, Any] | None = None) -> None:
        """Add a document to the index (in-memory only - call save() to persist)."""
        self._documents.append({
            "content": content,
            "metadata": metadata or {},
        })

    def save(self) -> None:
        """Persist the in-memory documents to disk."""
        if not self.index_path.exists():
            self.index_path.mkdir(parents=True, exist_ok=True)

        docs_file = self.index_path / "documents.json"
        with open(docs_file, "w") as f:
            json.dump(self._documents, f, indent=2)
        logger.info("rag_saved", count=len(self._documents))
