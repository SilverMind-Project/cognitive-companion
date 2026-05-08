"""Unit tests for :class:`~backend.integrations.triton_embedding_client.TritonEmbeddingClient`.

No real Triton server is required — all gRPC calls are intercepted by mocks.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.config import Settings
from backend.integrations.triton_embedding_client import (
    TritonEmbeddingClient,
    TritonEmbeddingError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_embedder(embeddings: list[list[float]] | None = None):
    """Build a mock TextEmbedder that returns *embeddings* from each call."""
    if embeddings is None:
        embeddings = [[0.1, 0.2, 0.3]]
    mock = MagicMock()
    mock.embed_query = AsyncMock(return_value=embeddings[0])
    mock.embed_chunks = AsyncMock(return_value=embeddings)
    return mock


def _make_mock_grpc_client():
    """Build a mock TritonGrpcClient that supports async context manager usage."""
    mock = MagicMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    return mock


# ---------------------------------------------------------------------------
# Constructor / dim
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_creates_without_connecting(self):
        """Constructor stores the dim but does not open any connection."""
        client = TritonEmbeddingClient()
        assert client._embedder is None

    def test_dim_default(self):
        """dim falls back to the package default when no settings override."""
        client = TritonEmbeddingClient()
        assert client.dim == 768

    def test_dim_from_settings(self):
        """dim is read from settings."""
        s = Settings.from_dict({"embedding": {"dim": 512}})
        with patch("backend.integrations.triton_embedding_client.settings", s):
            client = TritonEmbeddingClient()
            assert client.dim == 512


# ---------------------------------------------------------------------------
# embed_query
# ---------------------------------------------------------------------------


class TestEmbedQuery:
    async def test_embed_query_returns_embedding(self):
        """embed_query returns a float list on success."""
        mock_embedder = _make_mock_embedder([[0.1, 0.2, 0.3]])
        client = TritonEmbeddingClient()
        client._embedder = mock_embedder

        result = await client.embed_query("hello")
        assert result == [0.1, 0.2, 0.3]
        mock_embedder.embed_query.assert_awaited_once_with("hello")

    async def test_embed_query_connection_failure_raises(self):
        """When Triton is unreachable, embed_query raises TritonEmbeddingError."""
        client = TritonEmbeddingClient()

        with patch("triton_shared.client.grpc.TritonGrpcClient") as mock_grpc:
            mock_grpc.return_value.__aenter__ = AsyncMock(side_effect=OSError("connection refused"))

            with pytest.raises(TritonEmbeddingError, match="Failed to embed query"):
                await client.embed_query("hello")

    async def test_embed_query_model_error_raises(self):
        """When the model fails at inference time, embed_query raises."""
        mock_embedder = _make_mock_embedder()
        mock_embedder.embed_query = AsyncMock(side_effect=RuntimeError("model not ready"))
        client = TritonEmbeddingClient()
        client._embedder = mock_embedder

        with pytest.raises(TritonEmbeddingError, match="Failed to embed query"):
            await client.embed_query("hello")


# ---------------------------------------------------------------------------
# embed_chunks
# ---------------------------------------------------------------------------


class TestEmbedChunks:
    async def test_embed_chunks_returns_list_of_lists(self):
        """embed_chunks returns a list of float lists on success."""
        mock_embedder = _make_mock_embedder([[0.1, 0.2], [0.3, 0.4]])
        client = TritonEmbeddingClient()
        client._embedder = mock_embedder

        result = await client.embed_chunks(["a", "b"])
        assert result == [[0.1, 0.2], [0.3, 0.4]]

    async def test_embed_chunks_empty_list(self):
        """Empty input returns [] without touching the embedder."""
        mock_embedder = _make_mock_embedder()
        client = TritonEmbeddingClient()
        client._embedder = mock_embedder

        result = await client.embed_chunks([])
        assert result == []
        mock_embedder.embed_chunks.assert_not_called()

    async def test_embed_chunks_connection_failure_raises(self):
        """When Triton is unreachable, embed_chunks raises TritonEmbeddingError."""
        client = TritonEmbeddingClient()

        with patch("triton_shared.client.grpc.TritonGrpcClient") as mock_grpc:
            mock_grpc.return_value.__aenter__ = AsyncMock(side_effect=OSError("connection refused"))

            with pytest.raises(TritonEmbeddingError, match="Failed to embed chunks"):
                await client.embed_chunks(["a"])

    async def test_embed_chunks_batches_correctly(self):
        """Respects embedding.batch_size when splitting input."""
        mock_embedder = _make_mock_embedder()
        mock_embedder.embed_chunks = AsyncMock(side_effect=lambda batch: [[0.1]] * len(batch))

        s = Settings.from_dict({"embedding": {"batch_size": 2}})
        client = TritonEmbeddingClient()
        client._embedder = mock_embedder

        with patch("backend.integrations.triton_embedding_client.settings", s):
            result = await client.embed_chunks(["a", "b", "c"])

        assert len(result) == 3  # all items returned
        assert mock_embedder.embed_chunks.call_count == 2  # two batches: 2 + 1


# ---------------------------------------------------------------------------
# Lazy initialisation
# ---------------------------------------------------------------------------


class TestLazyInit:
    async def test_initialise_on_first_use(self):
        """The embedder is not created until embed_query or embed_chunks is called."""
        client = TritonEmbeddingClient()
        assert client._embedder is None

        mock_grpc = _make_mock_grpc_client()
        mock_embedder = _make_mock_embedder()

        with (
            patch(
                "triton_shared.client.grpc.TritonGrpcClient",
                return_value=mock_grpc,
            ),
            patch(
                "triton_shared.models.embedder.TextEmbedder",
                return_value=mock_embedder,
            ),
        ):
            await client.embed_query("hello")

        assert client._embedder is mock_embedder
