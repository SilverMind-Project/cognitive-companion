"""M08: BFF identity correction service — proxy, validation, error mapping."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.upstream_errors import UpstreamError
from backend.services.cts.identity_correction_service import (
    CorrectionContractError,
    CorrectionUpstreamError,
    IdentityCorrectionService,
)

pytestmark = pytest.mark.asyncio


def _proposal(**overrides) -> dict:
    raw = {
        "ph_id": "ph-1",
        "observation_ids": ["o1", "o2"],
        "start": {
            "observation_id": "o1",
            "captured_at": "2026-06-20T12:00:00+00:00",
            "reason": "segment_edge",
        },
        "end": {
            "observation_id": "o2",
            "captured_at": "2026-06-20T12:00:05+00:00",
            "reason": "association_discontinuity",
        },
        "ph_version": 3,
        "effective_identity_id": "amma",
    }
    raw.update(overrides)
    return raw


def _result(**overrides) -> dict:
    raw = {
        "revision_id": "rev-1",
        "correction_id": "corr-1",
        "ph_id": "ph-1",
        "previous_identity_id": "amma",
        "new_identity_id": "grandma",
        "range_id": "range-1",
        "new_ph_id": None,
        "job_status": "applying",
    }
    raw.update(overrides)
    return raw


def _service(client: MagicMock) -> IdentityCorrectionService:
    return IdentityCorrectionService(client)


async def test_propose_maps_person_id_and_boundaries() -> None:
    client = MagicMock()
    client.propose_segment = AsyncMock(return_value=_proposal())
    out = await _service(client).propose_segment(ph_id="ph-1")
    assert out.ph_version == 3
    assert out.effective_identity_id == "amma"
    # Effective identity is mapped onto the CC internal person_id at the boundary.
    assert out.person_id == "amma"
    assert out.start.reason == "segment_edge"
    assert out.observation_ids == ["o1", "o2"]


async def test_apply_injects_actor_and_never_trusts_browser() -> None:
    client = MagicMock()
    client.apply_segment_correction = AsyncMock(return_value=_result())
    svc = _service(client)
    # A browser-supplied actor must be overridden by the server actor.
    payload = {"ph_id": "ph-1", "reason_code": "wrong_person", "actor": "attacker"}
    await svc.apply_correction(payload=payload, actor="caregiver@home")

    sent = client.apply_segment_correction.call_args.kwargs["payload"]
    assert sent["actor"] == "caregiver@home"


async def test_apply_stale_version_propagates_409_code() -> None:
    client = MagicMock()
    body = json.dumps({"detail": {"code": "correction.stale_version", "message": "stale"}})
    client.apply_segment_correction = AsyncMock(
        side_effect=UpstreamError("tracking_orchestrator", 409, body)
    )
    with pytest.raises(CorrectionUpstreamError) as ei:
        await _service(client).apply_correction(payload={"ph_id": "ph-1"}, actor="x")
    assert ei.value.status == 409
    assert ei.value.code == "correction.stale_version"


async def test_upstream_5xx_becomes_502() -> None:
    client = MagicMock()
    client.propose_segment = AsyncMock(side_effect=UpstreamError("tracking_orchestrator", 503, ""))
    with pytest.raises(CorrectionUpstreamError) as ei:
        await _service(client).propose_segment(ph_id="ph-1")
    assert ei.value.status == 502


async def test_malformed_proposal_is_contract_error() -> None:
    client = MagicMock()
    client.propose_segment = AsyncMock(return_value={"ph_id": "ph-1"})  # missing fields
    with pytest.raises(CorrectionContractError):
        await _service(client).propose_segment(ph_id="ph-1")


async def test_get_job_passthrough() -> None:
    client = MagicMock()
    client.get_correction_job = AsyncMock(
        return_value={
            "revision_id": "rev-1",
            "job_id": "job-1",
            "status": "completed",
            "required_projections": ["cc"],
            "row_counts": {"cc": 4},
            "attempts": 1,
            "last_error": None,
        }
    )
    job = await _service(client).get_job(revision_id="rev-1")
    assert job.status == "completed"
    assert job.row_counts == {"cc": 4}
