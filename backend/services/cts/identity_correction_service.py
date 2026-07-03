"""BFF service for M08 segment corrections.

One service function powers the router and the MCP tool (D6 parity). It proxies
the orchestrator's M06 correction API, validates each upstream envelope (a
contract violation surfaces as a typed 502, never a silent empty result),
injects the audited actor server-side, and maps effective identity onto
Cognitive Companion's internal ``person_id`` at this boundary.

Upstream status semantics are preserved so the UI can react precisely: a stale
version token returns 409 with ``correction.stale_version`` (the composable
re-proposes and forces reconfirmation), an empty identity returns 422, and an
unknown PH/correction returns 404.
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from backend.core.upstream_errors import UpstreamError
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.schemas.cts_correction import (
    CorrectionJobResponse,
    CorrectionResultResponse,
    SegmentBoundaryView,
    SegmentProposalResponse,
)

logger = logging.getLogger(__name__)

_UPSTREAM = "tracking_orchestrator"


class CorrectionContractError(Exception):
    """Upstream returned a malformed correction envelope (rendered as 502)."""


class CorrectionUpstreamError(Exception):
    """Upstream rejected the correction with a meaningful status.

    Carries the upstream HTTP ``status`` and domain ``code`` so the router can
    re-raise them faithfully (e.g. 409 ``correction.stale_version``).
    """

    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _translate(exc: UpstreamError) -> CorrectionUpstreamError:
    """Map an UpstreamError to a status-preserving correction error.

    5xx becomes 502 (the upstream is the problem); 4xx is passed through with
    the orchestrator's domain ``detail.code`` when present so the UI can branch
    on stale-version / empty-identity / not-found precisely.
    """
    code = "correction.upstream"
    message = f"{exc.service} returned HTTP {exc.status}"
    try:
        detail = json.loads(exc.body).get("detail")
        if isinstance(detail, dict):
            code = str(detail.get("code") or code)
            message = str(detail.get("message") or message)
    except json.JSONDecodeError, AttributeError, TypeError:
        pass
    status = 502 if exc.status >= 500 else exc.status
    return CorrectionUpstreamError(status=status, code=code, message=message)


class IdentityCorrectionService:
    """Compose browser-facing correction responses from the orchestrator."""

    def __init__(self, client: OrchestratorClient) -> None:
        self._client = client

    async def propose_segment(
        self,
        *,
        ph_id: str,
        observation_id: str | None = None,
        at: str | None = None,
    ) -> SegmentProposalResponse:
        try:
            raw = await self._client.propose_segment(
                ph_id=ph_id, observation_id=observation_id, at=at
            )
        except UpstreamError as exc:
            raise _translate(exc) from exc
        try:
            start = raw["start"]
            end = raw["end"]
            proposal = SegmentProposalResponse(
                ph_id=raw["ph_id"],
                observation_ids=list(raw["observation_ids"]),
                start=SegmentBoundaryView(
                    observation_id=start["observation_id"],
                    captured_at=start["captured_at"],
                    reason=start["reason"],
                ),
                end=SegmentBoundaryView(
                    observation_id=end["observation_id"],
                    captured_at=end["captured_at"],
                    reason=end["reason"],
                ),
                ph_version=raw["ph_version"],
                effective_identity_id=raw.get("effective_identity_id"),
                person_id=raw.get("effective_identity_id"),
            )
        except (KeyError, TypeError, ValidationError) as exc:
            logger.error("correction propose contract violation from %s: %s", _UPSTREAM, exc)
            raise CorrectionContractError("malformed proposal envelope") from exc
        return proposal

    async def apply_correction(self, *, payload: dict, actor: str) -> CorrectionResultResponse:
        # Server-injected actor: never trust a browser-supplied subject.
        upstream_payload = {**payload, "actor": actor}
        try:
            raw = await self._client.apply_segment_correction(payload=upstream_payload)
        except UpstreamError as exc:
            raise _translate(exc) from exc
        return self._result(raw)

    async def compensate(self, *, correction_id: str, actor: str) -> CorrectionResultResponse:
        try:
            raw = await self._client.compensate_correction(correction_id=correction_id, actor=actor)
        except UpstreamError as exc:
            raise _translate(exc) from exc
        return self._result(raw)

    async def get_job(self, *, revision_id: str) -> CorrectionJobResponse:
        try:
            raw = await self._client.get_correction_job(revision_id=revision_id)
        except UpstreamError as exc:
            raise _translate(exc) from exc
        try:
            return CorrectionJobResponse(
                revision_id=raw["revision_id"],
                job_id=raw["job_id"],
                status=raw["status"],
                required_projections=list(raw["required_projections"]),
                row_counts=dict(raw["row_counts"]),
                attempts=raw["attempts"],
                last_error=raw.get("last_error"),
            )
        except (KeyError, TypeError, ValidationError) as exc:
            logger.error("correction job contract violation from %s: %s", _UPSTREAM, exc)
            raise CorrectionContractError("malformed job envelope") from exc

    @staticmethod
    def _result(raw: dict) -> CorrectionResultResponse:
        try:
            return CorrectionResultResponse(
                revision_id=raw["revision_id"],
                correction_id=raw["correction_id"],
                ph_id=raw["ph_id"],
                previous_identity_id=raw.get("previous_identity_id"),
                new_identity_id=raw.get("new_identity_id"),
                range_id=raw["range_id"],
                new_ph_id=raw.get("new_ph_id"),
                job_status=raw["job_status"],
            )
        except (KeyError, TypeError, ValidationError) as exc:
            logger.error("correction result contract violation from %s: %s", _UPSTREAM, exc)
            raise CorrectionContractError("malformed correction result envelope") from exc
