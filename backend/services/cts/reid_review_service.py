"""BFF service for the M09 ReID review queue.

One service function powers each thin route. It proxies the orchestrator's
governed gallery API, validates every upstream envelope (a malformed shape is a
typed 502, never a silent empty result), injects the audited actor server-side,
maps the effective identity onto Cognitive Companion's ``person_id``, and
presigns crop/full-frame media only when the object is still available.

Media is state-aware: a rejected candidate's crop object is deleted upstream, so
its ``crop_url`` is never presigned (the row keeps its key as an audit
fingerprint, but the browser must render a deleted-crop state, not a broken
image). Upstream status is preserved: a stale/ineligible candidate returns 409
with ``reid_review.stale``/``reid_review.ineligible`` so the composable can
re-fetch and disable a stale approval rather than show a generic error.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

from pydantic import ValidationError

from backend.core.upstream_errors import UpstreamError
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.schemas.cts_reid_review import (
    BatchRejectResponse,
    BatchRejectResultItem,
    EligibilityView,
    ReviewCandidateDetailResponse,
    ReviewCandidateListResponse,
    ReviewCandidateView,
    ReviewCountsResponse,
    ReviewEventsResponse,
    ReviewEventView,
)
from backend.services.cts.metrics import (
    cts_reid_review_action_latency_seconds,
    cts_reid_review_actions_total,
    cts_reid_review_failures_total,
    cts_reid_review_relabels_total,
)

logger = logging.getLogger(__name__)

_UPSTREAM = "tracking_orchestrator"

# Presign callable: maps a MinIO key (or None) to a URL (or None).
Presigner = Callable[[str | None], str | None]


class ReviewContractError(Exception):
    """Upstream returned a malformed review envelope (rendered as 502)."""


class ReviewUpstreamError(Exception):
    """Upstream rejected the review action with a meaningful status."""

    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _translate(exc: UpstreamError) -> ReviewUpstreamError:
    code = "reid_review.upstream"
    message = f"{exc.service} returned HTTP {exc.status}"
    try:
        detail = json.loads(exc.body).get("detail")
        if isinstance(detail, dict):
            code = str(detail.get("code") or code)
            message = str(detail.get("message") or message)
    except json.JSONDecodeError, AttributeError, TypeError:
        pass
    status = 502 if exc.status >= 500 else exc.status
    return ReviewUpstreamError(status=status, code=code, message=message)


def _no_presign(_key: str | None) -> str | None:
    return None


class ReIDReviewService:
    """Compose browser-facing review responses from the orchestrator."""

    def __init__(self, client: OrchestratorClient) -> None:
        self._client = client

    # -- reads ----------------------------------------------------------------

    async def list_candidates(
        self, *, params: dict[str, str], presign: Presigner = _no_presign
    ) -> ReviewCandidateListResponse:
        try:
            raw = await self._client.list_review_candidates(params)
        except UpstreamError as exc:
            raise _translate(exc) from exc
        try:
            return ReviewCandidateListResponse(
                candidates=[self._candidate(c, presign) for c in raw["candidates"]],
                total=raw["total"],
                limit=raw["limit"],
                offset=raw["offset"],
            )
        except (KeyError, TypeError, ValidationError) as exc:
            logger.error("reid review list contract violation from %s: %s", _UPSTREAM, exc)
            raise ReviewContractError("malformed candidate list envelope") from exc

    async def get_detail(
        self, candidate_id: str, *, presign: Presigner = _no_presign
    ) -> ReviewCandidateDetailResponse:
        try:
            raw = await self._client.get_review_candidate(candidate_id)
        except UpstreamError as exc:
            raise _translate(exc) from exc
        try:
            return ReviewCandidateDetailResponse(
                candidate=self._candidate(raw["candidate"], presign),
                events=[self._event(e) for e in raw["events"]],
                eligibility=self._eligibility(raw["eligibility"]),
            )
        except (KeyError, TypeError, ValidationError) as exc:
            logger.error("reid review detail contract violation from %s: %s", _UPSTREAM, exc)
            raise ReviewContractError("malformed candidate detail envelope") from exc

    async def list_events(self, candidate_id: str) -> ReviewEventsResponse:
        try:
            raw = await self._client.list_review_events(candidate_id)
        except UpstreamError as exc:
            raise _translate(exc) from exc
        try:
            return ReviewEventsResponse(events=[self._event(e) for e in raw["events"]])
        except (KeyError, TypeError, ValidationError) as exc:
            raise ReviewContractError("malformed events envelope") from exc

    async def counts(self) -> ReviewCountsResponse:
        try:
            raw = await self._client.get_review_counts()
        except UpstreamError as exc:
            raise _translate(exc) from exc
        try:
            return ReviewCountsResponse(
                pending_review=raw["pending_review"],
                operator_verified=raw["operator_verified"],
                rejected=raw["rejected"],
            )
        except (KeyError, TypeError, ValidationError) as exc:
            raise ReviewContractError("malformed counts envelope") from exc

    # -- mutations ------------------------------------------------------------

    async def approve(
        self,
        candidate_id: str,
        *,
        actor: str,
        base_audit_version: int,
        note: str | None,
        presign: Presigner = _no_presign,
    ) -> ReviewCandidateView:
        payload = {"actor": actor, "base_audit_version": base_audit_version, "note": note}
        return await self._mutate(
            "approve",
            lambda: self._client.approve_review_candidate(candidate_id, payload=payload),
            presign,
        )

    async def relabel(
        self,
        candidate_id: str,
        *,
        actor: str,
        base_audit_version: int,
        target_identity_id: str,
        note: str | None,
        presign: Presigner = _no_presign,
    ) -> ReviewCandidateView:
        payload = {
            "actor": actor,
            "base_audit_version": base_audit_version,
            "target_identity_id": target_identity_id,
            "note": note,
        }
        return await self._mutate(
            "relabel",
            lambda: self._client.relabel_review_candidate(candidate_id, payload=payload),
            presign,
        )

    async def reject(
        self,
        candidate_id: str,
        *,
        actor: str,
        base_audit_version: int,
        reason: str,
        note: str | None,
        presign: Presigner = _no_presign,
    ) -> ReviewCandidateView:
        payload = {
            "actor": actor,
            "base_audit_version": base_audit_version,
            "reason": reason,
            "note": note,
        }
        return await self._mutate(
            "reject",
            lambda: self._client.reject_review_candidate(candidate_id, payload=payload),
            presign,
        )

    async def reject_batch(
        self, *, actor: str, reason: str, note: str | None, items: list[dict]
    ) -> BatchRejectResponse:
        payload = {
            "actor": actor,
            "items": [
                {
                    "candidate_id": item["candidate_id"],
                    "base_audit_version": item["base_audit_version"],
                    "reason": reason,
                    "note": note,
                }
                for item in items
            ],
        }
        started = time.perf_counter()
        try:
            raw = await self._client.reject_review_batch(payload=payload)
        except UpstreamError as exc:
            cts_reid_review_failures_total.labels(action="reject_batch").inc()
            raise _translate(exc) from exc
        finally:
            cts_reid_review_action_latency_seconds.labels(action="reject_batch").observe(
                time.perf_counter() - started
            )
        cts_reid_review_actions_total.labels(action="reject_batch").inc()
        try:
            return BatchRejectResponse(
                results=[
                    BatchRejectResultItem(
                        candidate_id=r["candidate_id"],
                        ok=r["ok"],
                        error_code=r.get("error_code"),
                        error_message=r.get("error_message"),
                    )
                    for r in raw["results"]
                ],
                rejected=raw["rejected"],
                failed=raw["failed"],
            )
        except (KeyError, TypeError, ValidationError) as exc:
            raise ReviewContractError("malformed batch reject envelope") from exc

    async def compensate(
        self, candidate_id: str, *, actor: str, presign: Presigner = _no_presign
    ) -> ReviewCandidateView:
        return await self._mutate(
            "compensate",
            lambda: self._client.compensate_review_candidate(candidate_id, actor=actor),
            presign,
        )

    # -- internals ------------------------------------------------------------

    async def _mutate(self, action: str, call, presign: Presigner) -> ReviewCandidateView:
        started = time.perf_counter()
        try:
            try:
                raw = await call()
            except UpstreamError as exc:
                raise _translate(exc) from exc
            try:
                view = self._candidate(raw, presign)
            except (KeyError, TypeError, ValidationError) as exc:
                logger.error("reid review mutate contract violation from %s: %s", _UPSTREAM, exc)
                raise ReviewContractError("malformed candidate envelope") from exc
        except Exception:
            cts_reid_review_failures_total.labels(action=action).inc()
            raise
        finally:
            cts_reid_review_action_latency_seconds.labels(action=action).observe(
                time.perf_counter() - started
            )
        cts_reid_review_actions_total.labels(action=action).inc()
        if action == "relabel":
            cts_reid_review_relabels_total.inc()
        return view

    @staticmethod
    def _candidate(raw: dict, presign: Presigner) -> ReviewCandidateView:
        # Media is presigned only for a live object. A rejected candidate's crop
        # is deleted upstream, so never presign its key (would 404 in the browser).
        state = raw.get("state")
        crop_url = None if state == "rejected" else presign(raw.get("crop_key"))
        frame_url = None if state == "rejected" else presign(raw.get("source_frame_key"))
        return ReviewCandidateView(
            candidate_id=raw["candidate_id"],
            identity_id=raw.get("identity_id"),
            proposed_identity_id=raw.get("proposed_identity_id"),
            effective_identity_id=raw.get("effective_identity_id"),
            person_id=raw.get("effective_identity_id"),
            state=raw["state"],
            label_source=raw.get("label_source"),
            candidate_reason=raw.get("candidate_reason"),
            model_version=raw.get("model_version"),
            preprocessing_version=raw.get("preprocessing_version"),
            dimension=raw.get("dimension"),
            bbox=raw.get("bbox"),
            crop_width=raw.get("crop_width"),
            crop_height=raw.get("crop_height"),
            ph_id=raw.get("ph_id"),
            observation_id=raw.get("observation_id"),
            keyframe_id=raw.get("keyframe_id"),
            camera_id=raw.get("camera_id"),
            capture_time=raw.get("capture_time"),
            confidence=raw.get("confidence"),
            orientation=raw["orientation"],
            quality=raw["quality"],
            is_truncated=raw["is_truncated"],
            is_occluded=raw["is_occluded"],
            source_episode_id=raw.get("source_episode_id"),
            created_actor=raw.get("created_actor"),
            created_at=raw.get("created_at"),
            seen_at=raw.get("seen_at"),
            reviewed_actor=raw.get("reviewed_actor"),
            reviewed_time=raw.get("reviewed_time"),
            review_reason=raw.get("review_reason"),
            review_note=raw.get("review_note"),
            audit_version=raw["audit_version"],
            crop_url=crop_url,
            frame_url=frame_url,
        )

    @staticmethod
    def _event(raw: dict) -> ReviewEventView:
        return ReviewEventView(
            event_id=raw["event_id"],
            entry_id=raw["entry_id"],
            previous_state=raw["previous_state"],
            new_state=raw["new_state"],
            actor=raw["actor"],
            reason=raw.get("reason"),
            note=raw.get("note"),
            event_time=raw["event_time"],
            audit_version=raw["audit_version"],
        )

    @staticmethod
    def _eligibility(raw: dict) -> EligibilityView:
        return EligibilityView(
            eligible=raw["eligible"],
            model_compatible=raw["model_compatible"],
            reasons=list(raw["reasons"]),
        )
