"""Unit tests for the visitor methods on :class:`PersonIDClient`
(identity-continuity M07).

Every outbound call is intercepted by a mock ``httpx.AsyncClient`` so no real
person-identification-service is required. Unlike the rest of this client
(which returns ``None``/``[]`` on failure), the visitor methods raise
:class:`PersonIDUpstreamError` -- these tests assert that distinction.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.integrations.person_id_client import PersonIDClient, PersonIDUpstreamError

_HTTPX_TARGET = "backend.integrations.person_id_client.httpx.AsyncClient"

_CLUSTER = {
    "cluster_id": "c1",
    "status": "surfaced",
    "display_hint": None,
    "named_person_id": None,
    "sighting_count": 4,
    "distinct_days": 3,
    "first_seen_at": "2026-07-01T10:00:00+00:00",
    "last_seen_at": "2026-07-19T10:00:00+00:00",
    "recent_crop_keys": ["visitor-crops/c1/1.jpg"],
}


def _make_client(*, enabled: bool = True) -> PersonIDClient:
    client = PersonIDClient.__new__(PersonIDClient)
    client.base_url = "http://person-id-test"
    client.timeout = 5
    client.enabled = enabled
    return client


def _mock_http(json_payload, status_code: int = 200):
    response = MagicMock()
    response.status_code = status_code
    response.content = b"{}" if json_payload is not None else b""
    response.json.return_value = json_payload
    if status_code >= 400:
        import httpx

        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=response
        )
    else:
        response.raise_for_status = MagicMock()

    http_client = AsyncMock()
    http_client.request = AsyncMock(return_value=response)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=http_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestListAndGet:
    async def test_list_visitor_clusters_parses_summary(self):
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=_mock_http({"clusters": [_CLUSTER], "total": 1})):
            result = await client.list_visitor_clusters(status="surfaced")
        assert result.total == 1
        assert result.clusters[0].cluster_id == "c1"
        assert result.clusters[0].distinct_days == 3
        assert result.clusters[0].recent_crop_keys == ["visitor-crops/c1/1.jpg"]

    async def test_list_visitor_clusters_malformed_envelope_raises(self):
        client = _make_client()
        with (
            patch(_HTTPX_TARGET, return_value=_mock_http({"clusters": [{"status": "surfaced"}]})),
            pytest.raises(PersonIDUpstreamError) as exc_info,
        ):
            await client.list_visitor_clusters()
        assert exc_info.value.status == 502

    async def test_get_visitor_cluster_parses_detail_with_sightings(self):
        client = _make_client()
        detail = {
            **_CLUSTER,
            "recent_sightings": [
                {"seen_at": "2026-07-19T10:00:00+00:00", "quality": 0.9, "crop_object": "k1"}
            ],
        }
        with patch(_HTTPX_TARGET, return_value=_mock_http(detail)):
            result = await client.get_visitor_cluster("c1")
        assert result.cluster_id == "c1"
        assert len(result.recent_sightings) == 1
        assert result.recent_sightings[0].crop_object == "k1"

    async def test_get_visitor_cluster_not_found_raises_with_status(self):
        client = _make_client()
        with (
            patch(_HTTPX_TARGET, return_value=_mock_http({"detail": "not found"}, 404)),
            pytest.raises(PersonIDUpstreamError) as exc_info,
        ):
            await client.get_visitor_cluster("missing")
        assert exc_info.value.status == 404
        assert "not found" in exc_info.value.message


class TestMutations:
    async def test_name_visitor_cluster_success(self):
        client = _make_client()
        payload = {
            "cluster_id": "c1",
            "status": "named",
            "named_person_id": "nurse-priya",
            "member_name": "Nurse Priya",
            "embedding_count": 5,
        }
        with patch(_HTTPX_TARGET, return_value=_mock_http(payload)):
            result = await client.name_visitor_cluster("c1", "nurse-priya", "Nurse Priya")
        assert result.named_person_id == "nurse-priya"
        assert result.embedding_count == 5

    async def test_name_visitor_cluster_disabled_returns_409(self):
        client = _make_client()
        with (
            patch(
                _HTTPX_TARGET,
                return_value=_mock_http({"detail": "Visitor clustering is disabled"}, 409),
            ),
            pytest.raises(PersonIDUpstreamError) as exc_info,
        ):
            await client.name_visitor_cluster("c1", "nurse-priya", "Nurse Priya")
        assert exc_info.value.status == 409
        assert "disabled" in exc_info.value.message

    async def test_dismiss_visitor_cluster_success(self):
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=_mock_http({"cluster_id": "c1"})):
            await client.dismiss_visitor_cluster("c1")

    async def test_merge_visitor_clusters_success(self):
        client = _make_client()
        with patch(_HTTPX_TARGET, return_value=_mock_http(_CLUSTER)):
            result = await client.merge_visitor_clusters("c1", "c2")
        assert result.cluster_id == "c1"

    async def test_client_disabled_raises_service_unavailable(self):
        client = _make_client(enabled=False)
        with pytest.raises(PersonIDUpstreamError) as exc_info:
            await client.list_visitor_clusters()
        assert exc_info.value.status == 503

    async def test_timeout_raises_504(self):
        import httpx

        client = _make_client()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        with patch(_HTTPX_TARGET, return_value=ctx), pytest.raises(PersonIDUpstreamError) as exc_info:
            await client.list_visitor_clusters()
        assert exc_info.value.status == 504

    async def test_network_error_raises_502(self):
        import httpx

        client = _make_client()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("refused"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        with patch(_HTTPX_TARGET, return_value=ctx), pytest.raises(PersonIDUpstreamError) as exc_info:
            await client.list_visitor_clusters()
        assert exc_info.value.status == 502
