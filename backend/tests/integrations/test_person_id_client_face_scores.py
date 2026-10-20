"""PersonIDClient reads a face's raw cosine similarity, never the legacy ``confidence`` field.

The recorded response below is shaped like person-identification-service's ``/identify-batch``
output. Its unrecognized face shows why the field matters: the service clamps ``confidence`` to
0.0 there, while ``raw_similarity`` keeps the true (negative) cosine.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.integrations.person_id_client import PersonIDClient

_HTTPX_TARGET = "backend.integrations.person_id_client.httpx.AsyncClient"
_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "person_id" / "identify_batch_response.json"
)


def _client() -> PersonIDClient:
    client = PersonIDClient.__new__(PersonIDClient)
    client.base_url = "http://person-id-test"
    client.timeout = 5
    client.enabled = True
    return client


def _patched_post(payload: dict):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=response)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=http_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return patch(_HTTPX_TARGET, return_value=ctx)


@pytest.mark.asyncio
async def test_batch_faces_carry_raw_similarity_from_recorded_response() -> None:
    payload = json.loads(_FIXTURE.read_text())
    with _patched_post(payload):
        result = await _client().identify_batch(["aW1n"])

    assert result is not None
    recognized, unrecognized = result.frames[0]
    assert recognized.raw_similarity == 0.71
    assert unrecognized.raw_similarity == -0.04
    assert not hasattr(recognized, "confidence")


@pytest.mark.asyncio
async def test_older_service_without_raw_similarity_falls_back_to_similarity() -> None:
    payload = json.loads(_FIXTURE.read_text())
    for face in payload["frames"][0]["faces"]:
        del face["raw_similarity"]
    with _patched_post(payload):
        result = await _client().identify_batch(["aW1n"])

    assert result is not None
    assert [f.raw_similarity for f in result.frames[0]] == [0.71, -0.04]
