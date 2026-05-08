"""Thin wrapper around triton-shared's TextEmbedder for CC embedding needs.

Exposes ``embed_query(text) -> list[float]`` and ``embed_chunks(texts) -> list[list[float]]``
for ORM insertion. Failures raise ``TritonEmbeddingError`` caught by the
ingestion service and surfaced as 503 to the caller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.core.config import settings
from backend.core.logging import get_logger

if TYPE_CHECKING:
    from triton_shared.models.embedder import TextEmbedder

logger = get_logger(__name__)


class TritonEmbeddingError(RuntimeError):
    """Raised when embedding inference fails (Triton down, model not ready, etc.)."""


class TritonEmbeddingClient:
    """Constructs a triton-shared TextEmbedder from settings and exposes
    typed embedding helpers.

    The underlying client is lazy-initialized on first use so that the
    app can start even when Triton is temporarily unreachable.
    """

    def __init__(self) -> None:
        self._embedder: TextEmbedder | None = None
        self._dim: int = settings.get("embedding.dim", 768)

    @property
    def dim(self) -> int:
        return self._dim

    async def _ensure_embedder(self) -> TextEmbedder:
        if self._embedder is not None:
            return self._embedder

        from triton_shared.client.grpc import TritonGrpcClient
        from triton_shared.models.embedder import TextEmbedder

        triton_url = settings.get("embedding.triton_url", "") or "triton.nanai.khoofia.com:8701"
        model_name = settings.get("embedding.model_name", "embeddinggemma-300m")
        tokenizer_path = settings.get("embedding.tokenizer_path", "/opt/models/embeddinggemma/tokenizer.json")
        max_seq_len = settings.get("embedding.max_seq_len", 2048)

        client = TritonGrpcClient(url=triton_url)
        await client.__aenter__()
        self._embedder = TextEmbedder(
            client=client,
            model_name=model_name,
            tokenizer_path=tokenizer_path,
            max_seq_len=max_seq_len,
        )
        logger.info(
            "triton_embedding_client_initialized",
            url=triton_url,
            model=model_name,
            dim=self._dim,
        )
        return self._embedder

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string for vector search."""
        try:
            embedder = await self._ensure_embedder()
            return await embedder.embed_query(text)
        except Exception as exc:
            logger.error("triton_embed_query_error", error=str(exc))
            raise TritonEmbeddingError(f"Failed to embed query: {exc}") from exc

    async def embed_chunks(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text chunks, respecting ``embedding.batch_size``."""
        if not texts:
            return []
        batch_size = settings.get("embedding.batch_size", 16)
        all_embeddings: list[list[float]] = []
        try:
            embedder = await self._ensure_embedder()
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                chunk_embeddings = await embedder.embed_chunks(batch)
                all_embeddings.extend(chunk_embeddings)
            return all_embeddings
        except Exception as exc:
            logger.error("triton_embed_chunks_error", error=str(exc))
            raise TritonEmbeddingError(f"Failed to embed chunks: {exc}") from exc
